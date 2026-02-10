import json
import logging

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from config import Config
from constants import WEATHER_CODE_DESCRIPTIONS
from services import database
from utils.retry import retry_on_failure

logger = logging.getLogger(__name__)


class AlertService:
    """Service for generating weather alerts using AI"""

    def __init__(self):
        self.client = ChatOllama(
            model=Config.OLLAMA_MODEL,
            base_url=Config.OLLAMA_BASE_URL,
            temperature=0.2,
        )

    def parse_district_alerts(self, llm_text: str) -> dict[str, dict]:
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
                    # Handle "Region's Summary" separately if needed,
                    # or treat as special district
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
    def generate_alert(self, province: str, forecasts: dict[str, pd.DataFrame]) -> str:
        """
        Generate weather alerts for a province using AI in English and Urdu
        """
        forecast_texts = []
        for district, df in forecasts.items():
            # Optimize dataframe for prompt
            # Select only essential columns to save tokens
            df_prompt = df.copy()

            # Compact text format
            day_summaries = []
            for _, row in df_prompt.iterrows():
                # Basis: Date: Max/Min, Rain, Code
                summary = (
                    f"{row.get('Date', 'N/A')}: "
                    f"High {row.get('Max Temp (°C)', 'N/A')}°C/"
                    f"Low {row.get('Min Temp (°C)', 'N/A')}°C"
                )

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
            You are an expert meteorologist writing public weather advisories for {province}, Pakistan.

            INPUT (district forecasts):
            - The text below contains multiple district forecast blocks.
            - Each block starts with a district name (exact spelling) followed by its forecast details.
            - You MUST treat each district independently and must not mix forecasts between districts.

            FORECAST TEXT:
            {''.join(forecast_texts)}

            ABSOLUTE RULES (STRICT):
            1) NEVER write in question/answer format. NEVER ask questions. Use bulletin/advisory style only.
            2) Produce alerts for the FULL {forecast_days}-DAY PERIOD covered by the forecasts. Do NOT write single-day answers.
            - Each district alert must summarize the whole {forecast_days}-day period in 2–4 sentences.
            3) Output MUST be valid JSON ONLY. No markdown, no extra commentary, no leading/trailing text.
            4) JSON keys:
            - Include EXACTLY one top-level key per district found in the input.
            - District key names MUST match the district names in the input EXACTLY (spelling/case).
            - Also include EXACTLY one key named: "Region's Summary"
            - Do NOT add any other keys.
            5) For each district and the Region's Summary, output exactly two fields:
            - "english": string
            - "urdu": string
            No additional fields.
            6) Language & tone:
            - English: simple, clear, NDMA/PMD-style advisory tone.
            - Urdu: formal advisory Urdu (declarative), NOT conversational. No slang.
            7) Consistency:
            - Urdu must convey the SAME meaning as English (no missing/extra claims).
            8) NUMBERS:
            - Keep temperatures and dates as provided. Do not invent values.
            - If a range is present, state it as a range. If multiple days vary, summarize typical highs/lows.
            9) SAFETY / NON-ALARMIST:
            - If no significant hazards are indicated, say so clearly (e.g., "No severe weather indicated").
            - Only highlight hazards when supported by the forecast text.

            GLOSSARY ENFORCEMENT (URDU) — MUST FOLLOW EXACTLY:
            - You MUST use these exact Urdu terms (verbatim) for weather phenomena in the Urdu alert.
            - DO NOT transliterate English weather words into Urdu script (e.g., never write "اوورکاسٹ", "تھنڈر اسٹورم").
            - If a term appears in English, the Urdu MUST use the glossary term.

            Glossary (English -> Urdu EXACT):
            Thunderstorm: گرج چمک
            Rain: بارش
            Clear Sky: مطلع صاف
            Cloudy: ابر آلود / بادل
            Partly Cloudy: جزوی طور پر ابر آلود
            Sunny/Clear Skies: مطلع صاف
            Temperature: درجہ حرارت
            High: زیادہ سے زیادہ
            Low: کم سے کم
            Winds: ہوائیں
            Snow: برفباری
            Fog: دھند
            Smog: سموگ
            Haze: دھندلاہٹ
            Light Rain: ہلکی بارش
            Moderate Rain: معتدل بارش
            Heavy Rain: تیز بارش
            Very Heavy Rain: شدید بارش
            Extreme Rain: انتہائی شدید بارش
            Light Snow: ہلکی برفباری
            Moderate Snow: معتدل برفباری
            Heavy Snow: تیز برفباری
            Very Heavy Snow: شدید برفباری
            Extreme Snow: انتہائی شدید برفباری
            Light Thunderstorm: ہلکی گرج چمک
            Moderate Thunderstorm: معتدل گرج چمک
            Heavy Thunderstorm: تیز گرج چمک
            Very Heavy Thunderstorm: شدید گرج چمک
            Extreme Thunderstorm: انتہائی شدید گرج چمک
            Light Fog: ہلکی دھند
            Moderate Fog: معتدل دھند
            Heavy Fog: تیز دھند
            Very Heavy Fog: شدید دھند
            Extreme Fog: انتہائی شدید دھند
            Light Haze: ہلکی دھندلاہٹ
            Moderate Haze: معتدل دھندلاہٹ
            Heavy Haze: تیز دھندلاہٹ
            Very Heavy Haze: شدید دھندلاہٹ
            Extreme Haze: انتہائی شدید دھندلاہٹ
            Light Smog: ہلکی سموگ
            Moderate Smog: معتدل سموگ
            Heavy Smog: تیز سموگ
            Very Heavy Smog: شدید سموگ
            Extreme Smog: انتہائی شدید سموگ
            Overcast: مکمل ابر آلود

            REQUIRED OUTPUT JSON FORMAT (EXACT):
            {{
            "District Name 1": {{
                "english": "2–4 sentence {forecast_days}-day advisory for this district.",
                "urdu": "اسی معنی کے ساتھ 2–4 جملوں میں {forecast_days}-روزہ مشاورتی پیغام۔"
            }},
            "District Name 2": {{
                "english": "...",
                "urdu": "..."
            }},
            "Region's Summary": {{
                "english": "3–5 sentence province-wide summary for the full {forecast_days}-day period (key hazards + overall range + general advice).",
                "urdu": "اسی معنی کے ساتھ 3–5 جملوں میں صوبہ بھر کا خلاصہ۔"
            }}
            }}

            FINAL CHECK BEFORE YOU OUTPUT:
            - Valid JSON only (parsable).
            - No extra keys.
            - No Q/A phrasing.
            - Urdu uses glossary terms (no transliteration).
            - District alerts summarize {forecast_days} days, not a single day.
            """


        try:
            messages = [
                SystemMessage(
                    content=(
                            "You are an expert meteorologist generating public advisories for Pakistan.\n"
                            "STRICT OUTPUT: Return ONLY a single valid JSON object (start with '{' end with '}'). "
                            "No markdown, no commentary, no extra text.\n"
                            "JSON CONTRACT: Top-level keys must be exactly the district names provided in the input plus "
                            "\"Region's Summary\". Each key maps to an object with exactly two string fields: "
                            "\"english\" and \"urdu\". No extra fields.\n"
                            "STYLE: No question/answer format. Use declarative advisory tone.\n"
                            "URDU: Use Urdu script. Do not use Latin words in Urdu except numbers and °C. "
                            "Use the provided glossary EXACTLY; do not transliterate weather terms.\n"
                        )
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
        self, alerts: dict[str, dict], forecast_days: int, province: str
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

    def get_alert(self, province: str, district: str, days: int) -> dict | None:
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
                return {
                    "district": district,
                    "alert": {"english": alert_json, "urdu": ""},
                }
            except Exception as e:
                logger.error(f"Error parsing alert for {district}: {e}")
                return None

        return None

    def purge_cache(self, province: str, districts: list[str], days: int) -> int:
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
