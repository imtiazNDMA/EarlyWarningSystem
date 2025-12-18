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
        Parse district alerts from LLM response

        Args:
            llm_text: Raw text response from LLM

        Returns:
            Dict of district_name -> alert_text
        """
        alerts = {}

        # Pattern for: **District Name**: Alert description
        pattern = (
            r"\*\*([^*]+?)\*\*:\s*(.*?)(?=\s*\*\*|\s*Region's Summary|\Z)"
        )
        logger.debug(f"Raw LLM Response: {llm_text}")
        matches = re.findall(pattern, llm_text, re.DOTALL | re.MULTILINE)

        for district, msg in matches:
            d_name = district.strip()
            if d_name in alerts:
                alerts[d_name] += " " + msg.strip()
            else:
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
            forecast_texts.append(f"\n--- {district} ---\n{df.to_string(index=False)}")

        prompt = f"""
        Generate weather alerts for {province} based on these district forecasts:
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
                SystemMessage(content="You generate daily weather alerts for Pakistan. Always use the format: **DISTRICT_NAME**: followed by the alert description."),
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
        Save district-level alerts to cache files

        Args:
            alerts: Dict of district_name -> alert_text
            forecast_days: Number of forecast days
            province: Province name
        """
        import os

        os.makedirs("static/weatherdata", exist_ok=True)

        for district, msg in alerts.items():
            district_file = f"static/weatherdata/alert_{forecast_days}_{province}_{sanitize_filename(district)}.json"
            try:
                with open(district_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {"district": district, "alert": msg},
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )
                logger.debug(f"Saved alert for {province}/{district}")
            except Exception as e:
                logger.error(f"Error saving alert for {province}/{district}: {e}")

    def get_alert(self, province: str, district: str, days: int) -> Optional[dict]:
        """
        Get alert for a specific district

        Args:
            province: Province name
            district: District name
            days: Number of forecast days

        Returns:
            Alert data dict or None if not found
        """
        import os

        filename = f"static/weatherdata/alert_{days}_{province}_{sanitize_filename(district)}.json"
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Alert not found for {province}/{district}/{days}")
            return None
        except Exception as e:
            logger.error(f"Error loading alert for {province}/{district}/{days}: {e}")
            return None

    def purge_cache(self, province: str, districts: List[str], days: int) -> int:
        """
        Purge alert cache for specific districts
        
        Args:
            province: Province name
            districts: List of district names
            days: Forecast days
            
        Returns:
            Number of files deleted
        """
        import os
        count = 0
        for district in districts:
            filename = f"static/weatherdata/alert_{days}_{province}_{sanitize_filename(district)}.json"
            try:
                if os.path.exists(filename):
                    os.remove(filename)
                    count += 1
                    logger.info(f"Deleted alert cache file: {filename}")
            except Exception as e:
                logger.error(f"Error deleting alert cache file {filename}: {e}")
        return count
