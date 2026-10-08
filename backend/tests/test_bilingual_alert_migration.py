"""Migration coverage for preserving alert text while adding Urdu columns."""

import asyncio
import uuid
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config

from tests.conftest import ADMIN_URL

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def migrate(database_url: str, revision: str) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, revision)


def downgrade(database_url: str, revision: str) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(config, revision)


async def test_bilingual_migration_preserves_existing_alerts_and_downgrades() -> None:
    name = f"ews_migration_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(ADMIN_URL)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()

    raw_url = f"{ADMIN_URL.rsplit('/', 1)[0]}/{name}"
    database_url = raw_url.replace("postgresql://", "postgresql+asyncpg://")
    try:
        await asyncio.to_thread(migrate, database_url, "0005")
        connection = await asyncpg.connect(raw_url)
        try:
            await connection.execute(
                """
                INSERT INTO districts (id, name_en, province, lat, lon)
                VALUES ('lahore', 'Lahore', 'Punjab', 31.5, 74.3);
                INSERT INTO runs (
                    trigger, status, started_at, district_count, signal_count
                ) VALUES ('test', 'succeeded', now(), 1, 1);
                INSERT INTO alerts (
                    district_id, run_id, hazard, severity, urgency, certainty,
                    onset, expires, headline, body, instructions, generated_by,
                    evidence, status, issued_at
                ) VALUES (
                    'lahore', 1, 'heavy_rain', 'severe', 'expected', 'likely',
                    DATE '2026-10-08', DATE '2026-10-09', 'English headline',
                    'English body', 'English instructions', 'rules', '[]'::jsonb,
                    'active', now()
                );
                """
            )
        finally:
            await connection.close()

        await asyncio.to_thread(migrate, database_url, "0006")
        connection = await asyncpg.connect(raw_url)
        try:
            row = await connection.fetchrow(
                """
                UPDATE alerts
                SET headline_ur = 'لاہور کے لیے انتباہ'
                RETURNING headline_en, body_en, instructions_en, headline_ur
                """
            )
            assert row is not None
            assert dict(row) == {
                "headline_en": "English headline",
                "body_en": "English body",
                "instructions_en": "English instructions",
                "headline_ur": "لاہور کے لیے انتباہ",
            }
        finally:
            await connection.close()

        await asyncio.to_thread(downgrade, database_url, "0005")
        connection = await asyncpg.connect(raw_url)
        try:
            row = await connection.fetchrow(
                "SELECT headline, body, instructions FROM alerts"
            )
            assert row is not None
            assert dict(row) == {
                "headline": "English headline",
                "body": "English body",
                "instructions": "English instructions",
            }
        finally:
            await connection.close()
    finally:
        admin = await asyncpg.connect(ADMIN_URL)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()
