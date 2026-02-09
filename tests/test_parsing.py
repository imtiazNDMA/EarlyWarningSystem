import json
import logging

# Mock the logger
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def parse_district_alerts(llm_text: str) -> dict:
    """
    Parse district alerts from LLM response (expected to be JSON).
    """
    alerts = {}
    logger.debug(f"Parsing LLM Response of length: {len(llm_text)}")

    try:
        # Clean up the response to ensure it's valid JSON
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
                if district == "Region's Summary":
                    alerts["Region's Summary"] = content
                    continue

                if isinstance(content, dict):
                    english = content.get("english", "")
                    urdu = content.get("urdu", "")
                    alerts[district] = {"english": english, "urdu": urdu}
                elif isinstance(content, str):
                    alerts[district] = {"english": content, "urdu": ""}

        return alerts

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error parsing alerts: {e}")
        return {}


# Test Cases
def test_parsing():
    # Case 1: Pure JSON
    valid_json = """
    {
        "Lahore": {
            "english": "Heavy rain expected.",
            "urdu": "بھاری بارش متوقع ہے۔"
        },
        "Region's Summary": {
            "english": "Overall rainy.",
            "urdu": "مجموعی طور پر بارش۔"
        }
    }
    """
    parsed = parse_district_alerts(valid_json)
    print(
        "Test 1 (Valid JSON):",
        "PASSED"
        if "Lahore" in parsed and parsed["Lahore"]["urdu"] == "بھاری بارش متوقع ہے۔"
        else "FAILED",
    )

    # Case 2: Markdown JSON
    markdown_json = """
    Here is the weather report:
    ```json
    {
        "Islamabad": {
            "english": "Sunny.",
            "urdu": "دھوپ۔"
        }
    }
    ```
    Authentication complete.
    """
    parsed = parse_district_alerts(markdown_json)
    print(
        "Test 2 (Markdown JSON):",
        "PASSED"
        if "Islamabad" in parsed and parsed["Islamabad"]["urdu"] == "دھوپ۔"
        else "FAILED",
    )

    # Case 3: Mixed
    mixed_json = """
    {
        "Rawalpindi": "Legacy string format."
    }
    """
    parsed = parse_district_alerts(mixed_json)
    print(
        "Test 3 (Legacy String):",
        "PASSED"
        if "Rawalpindi" in parsed
        and parsed["Rawalpindi"]["english"] == "Legacy string format."
        else "FAILED",
    )


if __name__ == "__main__":
    test_parsing()
