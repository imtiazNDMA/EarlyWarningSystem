from unittest.mock import MagicMock, patch

from utils.health_check import check_lm_studio_status, check_mongodb_status


@patch("utils.health_check.requests.get")
def test_lm_studio_health_finds_configured_model(mock_get):
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "data": [{"id": "zai-org/glm-4.7-flash"}, {"id": "another-model"}]
    }
    mock_get.return_value = response

    healthy, message = check_lm_studio_status()

    assert healthy is True
    assert "zai-org/glm-4.7-flash" in message
    mock_get.assert_called_once_with("http://127.0.0.1:1234/v1/models", timeout=5)


@patch("utils.health_check.requests.get")
def test_lm_studio_health_fails_when_model_is_missing(mock_get):
    response = MagicMock(status_code=200)
    response.json.return_value = {"data": [{"id": "another-model"}]}
    mock_get.return_value = response

    healthy, message = check_lm_studio_status()

    assert healthy is False
    assert "NOT found" in message


def test_mongodb_health_uses_registered_repository(app):
    with app.app_context():
        healthy, message = check_mongodb_status()

    assert healthy is True
    assert "accessible" in message
