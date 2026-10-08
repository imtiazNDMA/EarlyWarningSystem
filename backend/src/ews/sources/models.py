"""ORM model for raw data fetched from external sources."""

import datetime as dt
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ews.core.db import Base


class SourceSnapshot(Base):
    """The raw payload one source returned for one district at one time.

    Snapshots are the evidence that forecasts and alerts point back to, so the
    payload is stored exactly as received.
    """

    __tablename__ = "source_snapshots"
    __table_args__ = (
        Index("ix_source_snapshots_latest", "district_id", "source", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    district_id: Mapped[str] = mapped_column(ForeignKey("districts.id"))
    source: Mapped[str] = mapped_column(String(40))
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
