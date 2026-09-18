"""Check LM Studio availability before starting the web application."""

import json
import os
import sys
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()
base_url = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
model = os.getenv("LM_STUDIO_MODEL", "zai-org/glm-4.7-flash")

try:
    with urllib.request.urlopen(  # noqa: S310 - Operator-configured local endpoint.
        f"{base_url}/models", timeout=3
    ) as response:
        payload = json.load(response)
except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
    print(f"[WARNING] LM Studio is unavailable at {base_url}: {exc}")
    print("[WARNING] Forecasts will work, but AI alert generation will fail.")
    print("[WARNING] Start LM Studio's local server before generating alerts.")
    sys.exit(0)

model_ids = [item.get("id") for item in payload.get("data", [])]
if model not in model_ids:
    print(f"[WARNING] LM Studio is running, but model '{model}' is unavailable.")
    print("[WARNING] Load the configured model in LM Studio before generating alerts.")
else:
    print(f"[INFO] LM Studio is ready with model '{model}'.")
