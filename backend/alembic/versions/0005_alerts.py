"""Create the alerts table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("district_id", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("hazard", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("urgency", sa.String(length=20), nullable=False),
        sa.Column("certainty", sa.String(length=20), nullable=False),
        sa.Column("onset", sa.Date(), nullable=False),
        sa.Column("expires", sa.Date(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("generated_by", sa.String(length=20), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["district_id"], ["districts.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["supersedes_id"], ["alerts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_district_status", "alerts", ["district_id", "status"])
    op.create_index("ix_alerts_issued_at", "alerts", ["issued_at"])


def downgrade() -> None:
    op.drop_index("ix_alerts_issued_at", table_name="alerts")
    op.drop_index("ix_alerts_district_status", table_name="alerts")
    op.drop_table("alerts")
