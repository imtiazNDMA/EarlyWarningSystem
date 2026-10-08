"""Add bilingual alert text columns.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("alerts", "headline", new_column_name="headline_en")
    op.alter_column("alerts", "body", new_column_name="body_en")
    op.alter_column("alerts", "instructions", new_column_name="instructions_en")
    op.add_column("alerts", sa.Column("headline_ur", sa.Text(), nullable=True))
    op.add_column("alerts", sa.Column("body_ur", sa.Text(), nullable=True))
    op.add_column("alerts", sa.Column("instructions_ur", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("alerts", "instructions_ur")
    op.drop_column("alerts", "body_ur")
    op.drop_column("alerts", "headline_ur")
    op.alter_column("alerts", "instructions_en", new_column_name="instructions")
    op.alter_column("alerts", "body_en", new_column_name="body")
    op.alter_column("alerts", "headline_en", new_column_name="headline")
