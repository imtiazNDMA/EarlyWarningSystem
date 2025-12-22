"""
Input validation utilities for the Early Warnings Weather Dashboard
"""

import re
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Allowed provinces
ALLOWED_PROVINCES = {
    "FEDERAL CAPITAL TERRITORY",
    "AZAD KASHMIR",
    "BALOCHISTAN",
    "INDIAN OCCUPIED KASHMIR",
    "GILGIT BALTISTAN",
    "KHYBER PAKHTUNKHWA",
    "PUNJAB",
    "SINDH",
}

# Safe filename pattern
SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-]+$")


def validate_province(province: str) -> bool:
    """Validate province name"""
    if not province or not isinstance(province, str):
        return False
    return province.strip() in ALLOWED_PROVINCES


def validate_district(district: str) -> bool:
    """Validate district name"""
    if not district or not isinstance(district, str):
        return False
    # Allow alphanumeric, spaces, hyphens, and underscores
    return bool(re.match(r"^[A-Za-z0-9\s\-_]+$", district.strip()))


def validate_forecast_days(days: int) -> bool:
    """Validate forecast days (1-7)"""
    try:
        days_int = int(days)
        return 1 <= days_int <= 7
    except (ValueError, TypeError):
        return False


def validate_district_list(districts: List[str], province: str) -> List[str]:
    """Validate and filter district list for a province"""
    if not districts or not isinstance(districts, list):
        return []

    # Import from models to avoid circular dependency
    from models import PROVINCES

    valid_districts = []
    province_districts = PROVINCES.get(province, {})

    for district in districts:
        if validate_district(district) and district in province_districts:
            valid_districts.append(district)

    return valid_districts


def sanitize_filename(name: str) -> str:
    """Sanitize filename to prevent path traversal"""
    if not name or not isinstance(name, str):
        return ""

    # Remove any path components to prevent directory traversal
    import os

    name = os.path.basename(name.strip())

    # Check if filename starts with dot before sanitizing
    starts_with_dot = name.startswith(".")

    # Replace any remaining unsafe characters
    sanitized = re.sub(r"[^A-Za-z0-9_\-]", "_", name)

    # Prevent empty filenames or filenames starting with dots
    if not sanitized or starts_with_dot:
        sanitized = "default_" + sanitized.lstrip("._")

    return sanitized


def validate_api_request_data(data: dict) -> tuple[bool, str]:
    """Validate API request data"""
    if not isinstance(data, dict):
        return False, "Invalid request data format"

    province = data.get("province")
    if not province or not validate_province(str(province)):
        return False, f"Invalid province: {province}"

    forecast_days = data.get("forecast_days", 1)
    if not validate_forecast_days(forecast_days):
        return False, f"Invalid forecast days: {forecast_days}"

    districts = data.get("districts", [])
    if districts and not isinstance(districts, list):
        return False, "Districts must be a list"

    # Validate district count to prevent resource exhaustion
    from config import Config

    max_districts = Config.MAX_DISTRICTS_PER_REQUEST
    if districts and len(districts) > max_districts:
        return (
            False,
            f"Too many districts. Maximum {max_districts} allowed per request.",
        )

    # Validate districts if provided
    if districts:
        valid_districts = validate_district_list(districts, str(province))
        if not valid_districts:
            return False, "No valid districts provided"
        data["districts"] = valid_districts  # Update with validated districts

    return True, "Valid"
