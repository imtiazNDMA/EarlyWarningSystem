"""
Tests for validation utilities
"""

import pytest
from utils.validation import (
    validate_province,
    validate_district,
    validate_forecast_days,
    sanitize_filename,
    validate_api_request_data
)


class TestValidation:
    """Test cases for validation utilities"""

    def test_validate_province_valid(self):
        """Test validating valid provinces"""
        assert validate_province("Punjab") is True
        assert validate_province("Sindh") is True
        assert validate_province("Balochistan") is True

    def test_validate_province_invalid(self):
        """Test validating invalid provinces"""
        assert validate_province("InvalidProvince") is False
        assert validate_province("") is False
        assert validate_province(None) is False
        assert validate_province(123) is False

    def test_validate_district_valid(self):
        """Test validating valid district names"""
        assert validate_district("Lahore") is True
        assert validate_district("Dera Ghazi Khan") is True
        assert validate_district("Muzaffarabad") is True

    def test_validate_district_invalid(self):
        """Test validating invalid district names"""
        assert validate_district("") is False
        assert validate_district(None) is False
        assert validate_district(123) is False
        assert validate_district("District@#$") is False

    def test_validate_forecast_days_valid(self):
        """Test validating valid forecast days"""
        assert validate_forecast_days(1) is True
        assert validate_forecast_days(3) is True
        assert validate_forecast_days(7) is True

    def test_validate_forecast_days_invalid(self):
        """Test validating invalid forecast days"""
        assert validate_forecast_days(0) is False
        assert validate_forecast_days(8) is False
        assert validate_forecast_days(-1) is False
        assert validate_forecast_days("invalid") is False
        assert validate_forecast_days(None) is False

    def test_sanitize_filename_valid(self):
        """Test sanitizing valid filenames"""
        assert sanitize_filename("test_file") == "test_file"
        assert sanitize_filename("test-file-123") == "test-file-123"

    def test_sanitize_filename_with_spaces(self):
        """Test sanitizing filenames with spaces"""
        result = sanitize_filename("test file name")
        assert " " not in result
        assert result == "test_file_name"

    def test_sanitize_filename_with_special_chars(self):
        """Test sanitizing filenames with special characters"""
        result = sanitize_filename("test@file#name.txt")
        assert "@" not in result
        assert "#" not in result
        assert "." not in result

    def test_sanitize_filename_path_traversal(self):
        """Test sanitizing filenames with path traversal attempts"""
        result = sanitize_filename("../../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_sanitize_filename_empty(self):
        """Test sanitizing empty filename"""
        result = sanitize_filename("")
        assert result == ""

    def test_sanitize_filename_dot_prefix(self):
        """Test sanitizing filename starting with dot"""
        result = sanitize_filename(".hidden")
        assert result.startswith("default_")

    def test_validate_api_request_data_valid(self):
        """Test validating valid API request data"""
        data = {
            "province": "Punjab",
            "districts": ["Lahore", "Faisalabad"],
            "forecast_days": 3
        }
        
        is_valid, message = validate_api_request_data(data)
        assert is_valid is True

    def test_validate_api_request_data_invalid_province(self):
        """Test validating API request with invalid province"""
        data = {
            "province": "InvalidProvince",
            "forecast_days": 3
        }
        
        is_valid, message = validate_api_request_data(data)
        assert is_valid is False
        assert "province" in message.lower()

    def test_validate_api_request_data_invalid_days(self):
        """Test validating API request with invalid forecast days"""
        data = {
            "province": "Punjab",
            "forecast_days": 10
        }
        
        is_valid, message = validate_api_request_data(data)
        assert is_valid is False
        assert "forecast days" in message.lower()

    def test_validate_api_request_data_not_dict(self):
        """Test validating non-dict API request data"""
        is_valid, message = validate_api_request_data("not a dict")
        assert is_valid is False
