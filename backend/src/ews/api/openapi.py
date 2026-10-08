"""Export the OpenAPI schema that the frontend's API types are generated from.

Run ``python -m ews.api.openapi`` from ``backend/`` after changing any endpoint,
then ``npm run generate:api`` in ``frontend/``.
"""

import json
from pathlib import Path

from ews.api.app import create_app
from ews.core.settings import Settings

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "openapi.json"


def render_schema() -> str:
    """Return the application's OpenAPI schema as stable, readable JSON."""
    schema = create_app(Settings()).openapi()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    SCHEMA_PATH.write_text(render_schema(), encoding="utf-8", newline="\n")
