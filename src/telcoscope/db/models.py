"""SQLAlchemy models for the telcoscope schema.

Models are grouped by logical schema (dims, raw, analytics). Marts are built
by dbt and are deliberately not modelled here — that's the point of the
transformation-layer separation.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Double,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    Text,
    TIMESTAMP,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Common declarative base for all telcoscope tables."""


# --- Dimension tables (schema: dims) --------------------------------------

class Vendor(Base):
    __tablename__ = "dim_vendor"
    __table_args__ = {"schema": "dims"}

    vendor_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)


class Technology(Base):
    __tablename__ = "dim_technology"
    __table_args__ = {"schema": "dims"}

    technology_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    technology: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    release: Mapped[str | None] = mapped_column(Text)


class Counter(Base):
    __tablename__ = "dim_counter"
    __table_args__ = {"schema": "dims"}

    counter_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kpi_group: Mapped[str | None] = mapped_column(Text)
    vendor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("dims.dim_vendor.vendor_id")
    )
    vendor_counter_name: Mapped[str | None] = mapped_column(Text)
    technology_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("dims.dim_technology.technology_id")
    )
    unit: Mapped[str | None] = mapped_column(Text)


class Enb(Base):
    __tablename__ = "dim_enb"
    __table_args__ = {"schema": "dims"}

    enb_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enb_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    vendor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dims.dim_vendor.vendor_id"), nullable=False
    )
    region: Mapped[str | None] = mapped_column(Text)
    site_id: Mapped[str | None] = mapped_column(Text)


class Cell(Base):
    __tablename__ = "dim_cell"
    __table_args__ = {"schema": "dims"}

    cell_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cell_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    enb_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dims.dim_enb.enb_id"), nullable=False
    )
    sector: Mapped[int | None] = mapped_column(Integer)
    earfcn: Mapped[int | None] = mapped_column(Integer)
    archetype: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Double)
    longitude: Mapped[float | None] = mapped_column(Double)
    azimuth_deg: Mapped[float | None] = mapped_column(Double)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


# --- Raw tables (schema: raw) ---------------------------------------------

class PmMeasurement(Base):
    __tablename__ = "pm_measurements"
    __table_args__ = (
        PrimaryKeyConstraint("ts", "cell_id", "counter_id"),
        {"schema": "raw"},
    )

    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    enb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cell_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    counter_id: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[float | None] = mapped_column(Double)
    gran_period_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)


class FmAlarm(Base):
    __tablename__ = "fm_alarms"
    __table_args__ = {"schema": "raw"}

    alarm_uid: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    raised_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    cleared_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    enb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cell_id: Mapped[int | None] = mapped_column(BigInteger)
    alarm_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONB)


class CmChange(Base):
    __tablename__ = "cm_changes"
    __table_args__ = {"schema": "raw"}

    change_uid: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cell_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parameter: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(Text)


# --- Analytics tables (schema: analytics) ----------------------------------

class SynthTruth(Base):
    """Ground-truth labels for injected anomalies. Used to evaluate detectors."""

    __tablename__ = "synth_truth"
    __table_args__ = {"schema": "analytics"}

    truth_uid: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pattern_type: Mapped[str] = mapped_column(Text, nullable=False)
    cell_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ts_start: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    ts_end: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    kpi_affected: Mapped[str] = mapped_column(Text, nullable=False)
    magnitude: Mapped[float] = mapped_column(Double, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)