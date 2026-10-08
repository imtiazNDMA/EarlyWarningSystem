"""ORM model for the district registry."""

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from ews.core.db import Base


class District(Base):
    """A district that forecasts and alerts are produced for."""

    __tablename__ = "districts"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name_en: Mapped[str] = mapped_column(String(120))
    name_ur: Mapped[str | None] = mapped_column(String(120))
    province: Mapped[str] = mapped_column(String(80), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    # Join key into the packaged boundary file; null when no boundary matches
    feature_id: Mapped[str | None] = mapped_column(String(80), unique=True)
