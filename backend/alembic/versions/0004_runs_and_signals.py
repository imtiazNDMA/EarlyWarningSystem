"""Create the runs and hazard_signals tables.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("district_count", sa.Integer(), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_status", "runs", ["status"])

    op.create_table(
        "hazard_signals",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("district_id", sa.String(length=80), nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("hazard", sa.String(length=40), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("onset", sa.Date(), nullable=False),
        sa.Column("expires", sa.Date(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["district_id"], ["districts.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["snapshot_id"], ["source_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hazard_signals_run_id", "hazard_signals", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_hazard_signals_run_id", table_name="hazard_signals")
    op.drop_table("hazard_signals")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_table("runs")
