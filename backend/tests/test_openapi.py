"""Tests for the exported OpenAPI schema."""

from ews.api.openapi import SCHEMA_PATH, render_schema


class TestExportedSchema:
    """The committed schema is what the frontend's API types are generated from."""

    def test_committed_schema_is_up_to_date(self) -> None:
        assert SCHEMA_PATH.read_text(encoding="utf-8") == render_schema()
