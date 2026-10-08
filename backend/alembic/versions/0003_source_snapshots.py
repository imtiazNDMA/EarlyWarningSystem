"""Create the source_snapshots table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("district_id", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["district_id"], ["districts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_source_snapshots_latest",
        "source_snapshots",
        ["district_id", "source", "fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_source_snapshots_latest", table_name="source_snapshots")
    op.drop_table("source_snapshots")
