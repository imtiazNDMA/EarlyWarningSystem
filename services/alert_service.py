import re
import json
import logging
from typing import Dict, List, Optional
import pandas as pd
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from config import Config
from utils.validation import sanitize_filename
from utils.retry import retry_on_failure
import database
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

    def parse_district_alerts(self, llm_text: str) -> Dict[str, str]:
        """
        Parse district alerts from LLM response using streaming approach for better performance

        Args:
            llm_text: Raw text response from LLM

        Returns:
            Dict of district_name -> alert_text
        """
        alerts = {}
        logger.debug(f"Parsing LLM Response of length: {len(llm_text)}")

        # Streaming parser - split by ** markers instead of complex regex
        # This is more efficient than regex on large texts
        sections = llm_text.split("**")

        current_district = None
        current_alert = ""

        for i, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue

            # First section might be before any ** markers
            if i == 0 and not section.startswith("**"):
                continue

            # Split district name from alert content
            if ":" in section:
                district_part, alert_part = section.split(":", 1)
                district_name = district_part.strip()
                alert_content = alert_part.strip()

                # Check if this looks like a valid district entry (non-empty district name)
                if district_name and not district_name.lower().startswith("region"):
                    if district_name in alerts:
                        alerts[district_name] += " " + alert_content
                    else:
                        alerts[district_name] = alert_content

        # Fallback: try regex if streaming parser didn't find alerts
        if not alerts:
            logger.debug("Streaming parser found no alerts, trying regex fallback")
            pattern = r"\*\*([^*]+?)\*\*:\s*(.*?)(?=\s*\*\*|\s*Region's Summary|\Z)"
            matches = re.findall(pattern, llm_text, re.DOTALL | re.MULTILINE)

            for district, msg in matches:
                d_name = district.strip()
                if d_name:
                    alerts[d_name] = msg.strip()

        logger.debug(f"Parsed {len(alerts)} district alerts")
        return alerts

    @retry_on_failure(max_attempts=3, delay=2.0, backoff=2.0)
    def generate_alert(self, province: str, forecasts: Dict[str, pd.DataFrame]) -> str:
        """
        Generate weather alerts for a province using AI

        Args:
            province: Province name
            forecasts: Dict of district_name -> forecast_dataframe

        Returns:
            Generated alert text
        """
        forecast_texts = []
        for district, df in forecasts.items():
            # Optimize dataframe for prompt - select only essential columns to save tokens
            # Create a copy to avoid modifying the original
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

            district_text = f"\n--- {district} ---\n" + "\n".join(day_summaries)
            forecast_texts.append(district_text)

        prompt = f"""
        Act as an expert meteorologist and generate weather alerts for {province} based on these district forecasts:
        {"".join(forecast_texts)}

        Rules:
        - Write a short alert for each district.
        - Use this exact format for each district: **DISTRICT_NAME**: Alert description here.
        - End with a region's summary.
        - Make sure to use the exact district names as provided.

        Example format:
        **Islamabad**: Expect sunny weather with highs of 25°C.
        **Rawalpindi**: Partly cloudy with chance of light rain.

        Region's Summary: Overall conditions...
        """

        try:
            messages = [
                SystemMessage(
                    content="Act as an expert meteorologist and generate daily weather alerts for Pakistan. Always use the format: **DISTRICT_NAME**: followed by the alert description."
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
        self, alerts: Dict[str, str], forecast_days: int, province: str
    ):
        """
        Save district-level alerts to SQLite database

        Args:
            alerts: Dict of district_name -> alert_text
            forecast_days: Number of forecast days
            province: Province name
        """

        for district, msg in alerts.items():
            database.save_alert(province, district, forecast_days, msg)
            logger.debug(f"Saved DB alert for {province}/{district}")

    def get_alert(self, province: str, district: str, days: int) -> Optional[dict]:
        """
        Get alert for a specific district from SQLite

        Args:
            province: Province name
            district: District name
            days: Number of forecast days

        Returns:
            Alert data dict or None if not found
        """

        alert_text = database.get_alert(province, district, days)
        if alert_text:
            return {"district": district, "alert": alert_text}

        # Fallback to check if legacy file exists (optional, maybe not needed if we want fully clean switch)
        # For now, let's just return None to encourage DB usage
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
