import re
import logging
import json
from typing import Dict, List, Optional
import pandas as pd
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from config import Config
from utils.retry import retry_on_failure
from services import database
from constants import WEATHER_CODE_DESCRIPTIONS

logger = logging.getLogger(__name__)


class AlertService:
    """Service for generating weather alerts using AI"""

    def __init__(self):
        self.client = ChatOllama(
            model=Config.OLLAMA_MODEL,
            base_url=Config.OLLAMA_BASE_URL,
            temperature=0.3,
        )

    def parse_district_alerts(self, llm_text: str) -> Dict[str, dict]:
        """
        Parse district alerts from LLM response (expected to be JSON).
        
        Args:
            llm_text: Raw text response from LLM
            
        Returns:
            Dict of district_name -> {"english": "...", "urdu": "..."}
        """
        alerts = {}
        logger.debug(f"Parsing LLM Response of length: {len(llm_text)}")
        
        try:
            # Clean up the response to ensure it's valid JSON
            # Sometimes LLMs add markdown code blocks
            cleaned_text = llm_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            
            cleaned_text = cleaned_text.strip()
            
            # Find the JSON object if there's extra text
            start_idx = cleaned_text.find("{")
            end_idx = cleaned_text.rfind("}")
            
            if start_idx != -1 and end_idx != -1:
                json_str = cleaned_text[start_idx : end_idx + 1]
                data = json.loads(json_str)
                
                # Normalize keys (district names)
                for district, content in data.items():
                    # Handle "Region's Summary" separately if needed, or treat as special district
                    if district == "Region's Summary":
                        alerts["Region's Summary"] = content
                        continue
                        
                    # Ensure content has english and urdu keys
                    if isinstance(content, dict):
                        english = content.get("english", "")
                        urdu = content.get("urdu", "")
                        alerts[district] = {"english": english, "urdu": urdu}
                    elif isinstance(content, str):
                        # Fallback for simple string
                        alerts[district] = {"english": content, "urdu": ""}
                        
            return alerts

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            logger.debug(f"Raw response: {llm_text}")
            # Fallback to empty dict or try a regex rescue if needed
            return {}
        except Exception as e:
            logger.error(f"Error parsing alerts: {e}")
            return {}

    @retry_on_failure(max_attempts=3, delay=2.0, backoff=2.0)
    def generate_alert(self, province: str, forecasts: Dict[str, pd.DataFrame]) -> str:
        """
        Generate weather alerts for a province using AI in English and Urdu
        """
        forecast_texts = []
        for district, df in forecasts.items():
            # Optimize dataframe for prompt - select only essential columns to save tokens
            df_prompt = df.copy()

            # Compact text format
            day_summaries = []
            for _, row in df_prompt.iterrows():
                # Basis: Date: Max/Min, Rain, Code
                summary = f"{row.get('Date', 'N/A')}: High {row.get('Max Temp (°C)', 'N/A')}°C/Low {row.get('Min Temp (°C)', 'N/A')}°C"

                # Add conditionals
                if "Precipitation (mm)" in row and row["Precipitation (mm)"] > 0:
                    summary += f", Rain {row['Precipitation (mm)']}mm"

                if "Weather Code" in row:
                    code = int(row["Weather Code"])
                    description = WEATHER_CODE_DESCRIPTIONS.get(
                        code, f"Unknown weather (Code {code})"
                    )
                    summary += f", {description}"

                day_summaries.append(summary)

            district_text = f"District: {district}\n" + "\n".join(day_summaries)
            forecast_texts.append(district_text)

        prompt = f"""
        Act as an expert meteorologist and generate weather alerts for {province} based on these district forecasts:
        
        {"".join(forecast_texts)}

        Rules:
        1.  Analyze the forecast for each district.
        2.  Generate a concise alert in **English**.
        3.  Generate a concise alert in **Urdu**.
        4.  Provide a **"Region's Summary"** for the overall province.
        5.  **Output MUST be valid JSON only.** No markdown formatting, no intro text.
        6.  The alert should be generated for 7 days, covering the whole forecast period.
        7.  The alert should be generated for each district in the province.
        8.  Maintain a smooth and steady flow of information, using simple and easy to understand language.
        9.  Explain it like a story, not like a technical report.
        
        **URDU TRANSLATION GLOSSARY (STRICTLY FOLLOW THIS):**
        - Thunderstorm: گرج چمک (Garaj Chamak) - NEVER use "Tezaab" (Acid).
        - Rain: بارش (Barish)
        - Heavy Rain: موسلا دھار بارش (Mosla dhaar barish)
        - Cloudy: ابر آلود (Abr Aalood) / بادل (Baadal)
        - Partly Cloudy: جزوی طور پر ابر آلود (Juzwi tor par abr aalood)
        - Sunny: دھوپ (Dhoop) / مطلع صاف (Matla Saaf)
        - Temperature: درجہ حرارت (Darja Hararat)
        - High: زیادہ سے زیادہ (Zyada se zyada)
        - Low: کم سے کم (Kam se kam)
        - Winds: ہوائیں (Hawayein)
        - Snow: برفباری (Baraf bari)
        - Fog/Smog: دھند (Dhund) / سموگ (Smog)
        - Haze: دھندلاہٹ (Dhundlahat)

        JSON Structure:
        {{
            "District Name 1": {{
                "english": "English alert text here...",
                "urdu": "اردو متن یہاں..."
            }},
            "District Name 2": {{
                "english": "...",
                "urdu": "..."
            }},
            "Region's Summary": {{
                 "english": "...",
                 "urdu": "..."
            }}
        }}
        """

        try:
            messages = [
                SystemMessage(
                    content="You are a weather assistant. Output only valid JSON. Ensure Urdu translations are accurate, natural, and use the provided glossary. Avoid literal translations that change the meaning (e.g. Thunderstorm is NOT Tezaab)."
                ),
                HumanMessage(content=prompt),
            ]
            response = self.client.invoke(messages)
            alert_text = response.content

            logger.info(f"Generated alerts for {province} ({len(forecasts)} districts)")
            return alert_text

        except Exception as e:
            logger.error(f"Error generating alerts for {province}: {e}")
            raise

    def save_district_alerts(
        self, alerts: Dict[str, dict], forecast_days: int, province: str
    ):
        """
        Save district-level alerts to SQLite database
        
        Args:
            alerts: Dict of district_name -> {"english": "...", "urdu": "..."}
        """

        for district, content in alerts.items():
            # Serialize the content dict to a JSON string for storage
            msg_json = json.dumps(content, ensure_ascii=False)
            database.save_alert(province, district, forecast_days, msg_json)
            logger.debug(f"Saved DB alert for {province}/{district}")

    def get_alert(self, province: str, district: str, days: int) -> Optional[dict]:
        """
        Get alert for a specific district from SQLite
        """

        alert_json = database.get_alert(province, district, days)
        if alert_json:
            try:
                # Try to parse it as JSON (new format)
                alert_data = json.loads(alert_json)
                return {"district": district, "alert": alert_data}
            except json.JSONDecodeError:
                # Fallback for legacy text-only alerts
                return {"district": district, "alert": {"english": alert_json, "urdu": ""}}
            except Exception as e:
                logger.error(f"Error parsing alert for {district}: {e}")
                return None

        return None

    def purge_cache(self, province: str, districts: List[str], days: int) -> int:
        """
        Purge alert cache for specific districts (Delegated to database module)

        Args:
            province: Province name
            districts: List of district names
            days: Forecast days

        Returns:
            Number of files/rows deleted
        """
        return database.purge_cache_db(province, districts, days)
