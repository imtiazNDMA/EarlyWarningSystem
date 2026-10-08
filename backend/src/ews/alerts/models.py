"""ORM model for alerts."""

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ews.core.db import Base


class Alert(Base):
    """A warning issued for one district and hazard.

    Alerts are records. What an alert says never changes after it is issued;
    when conditions change it is ended (``status`` and ``ended_at``) and, where
    needed, a new alert that points back to it is issued.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_district_status", "district_id", "status"),
        Index("ix_alerts_issued_at", "issued_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    district_id: Mapped[str] = mapped_column(ForeignKey("districts.id"))
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    hazard: Mapped[str] = mapped_column(String(40))
    # Common Alerting Protocol vocabulary
    severity: Mapped[str] = mapped_column(String(20))
    urgency: Mapped[str] = mapped_column(String(20))
    certainty: Mapped[str] = mapped_column(String(20))
    onset: Mapped[dt.date] = mapped_column(Date)
    expires: Mapped[dt.date] = mapped_column(Date)
    headline_en: Mapped[str] = mapped_column(Text)
    body_en: Mapped[str] = mapped_column(Text)
    instructions_en: Mapped[str] = mapped_column(Text)
    headline_ur: Mapped[str | None] = mapped_column(Text)
    body_ur: Mapped[str | None] = mapped_column(Text)
    instructions_ur: Mapped[str | None] = mapped_column(Text)
    # What wrote the text: "rules" for templates
    generated_by: Mapped[str] = mapped_column(String(20))
    # Values that justify the alert, each pointing at a source snapshot:
    # snapshot_id, metric, unit, date, value, threshold
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    # active, superseded, cancelled or expired
    status: Mapped[str] = mapped_column(String(20))
    issued_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"))
