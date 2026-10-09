"""Add the reasons an alert was held instead of published.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alerts", sa.Column("held_reasons", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("alerts", "held_reasons")
