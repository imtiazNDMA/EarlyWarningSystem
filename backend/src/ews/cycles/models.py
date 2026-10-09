"""ORM models for monitoring cycles and the hazard signals they produce."""

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ews.core.db import Base


class Run(Base):
    """One monitoring cycle: fetch every source, then screen every district."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    trigger: Mapped[str] = mapped_column(String(20))
    # running, succeeded or failed
    status: Mapped[str] = mapped_column(String(20), index=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    district_count: Mapped[int] = mapped_column(Integer, default=0)
    signal_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class RunEvent(Base):
    """One entry in a run's ordered log of what it did."""

    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "seq"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    # Position within the run, from 1
    seq: Mapped[int] = mapped_column(Integer)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    # See ews.cycles.events.EventType
    type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class HazardSignal(Base):
    """A hazard threshold that a district's forecast reached during a run."""

    __tablename__ = "hazard_signals"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    district_id: Mapped[str] = mapped_column(ForeignKey("districts.id"))
    # The forecast this signal was screened from
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("source_snapshots.id"))
    hazard: Mapped[str] = mapped_column(String(40))
    level: Mapped[str] = mapped_column(String(20))
    onset: Mapped[dt.date] = mapped_column(Date)
    expires: Mapped[dt.date] = mapped_column(Date)
    # What triggered it: metric, unit, peak_value, peak_date, threshold, days_over
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB)
