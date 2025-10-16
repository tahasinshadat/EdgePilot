# edgepilot/models.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
from typing import Optional

from sqlalchemy import (
    String, Integer, Float, Boolean, Text, DateTime, ForeignKey, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_id() -> str:
    return f"R-{utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def task_id() -> str:
    return f"T-{utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=run_id)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    user_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")
    summary_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    metrics: Mapped[list["Metric"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class Metric(Base):
    __tablename__ = "metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=utcnow)

    cpu_total_pct: Mapped[float] = mapped_column(Float, default=0.0)
    mem_used_bytes: Mapped[int] = mapped_column(Integer, default=0)
    swap_used_bytes: Mapped[int] = mapped_column(Integer, default=0)

    net_rx_bytes: Mapped[int] = mapped_column(Integer, default=0)
    net_tx_bytes: Mapped[int] = mapped_column(Integer, default=0)
    disk_read_bytes: Mapped[int] = mapped_column(Integer, default=0)
    disk_write_bytes: Mapped[int] = mapped_column(Integer, default=0)

    gpu_util_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gpu_mem_used_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    power_watts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    battery_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    json_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Optional association to a run (not in original schema, but helpful)
    run_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=True)
    run: Mapped[Optional["Run"]] = relationship(back_populates="metrics")


Index("ix_metrics_ts", Metric.ts)


class ProcessMetric(Base):
    __tablename__ = "process_metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=utcnow)

    pid: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String)
    cpu_pct: Mapped[float] = mapped_column(Float, default=0.0)
    rss_bytes: Mapped[int] = mapped_column(Integer, default=0)
    io_read_bytes: Mapped[int] = mapped_column(Integer, default=0)
    io_write_bytes: Mapped[int] = mapped_column(Integer, default=0)
    threads: Mapped[int] = mapped_column(Integer, default=0)
    cmdline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


Index("ix_process_metrics_ts", ProcessMetric.ts)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=task_id)
    name: Mapped[str] = mapped_column(String)
    command: Mapped[str] = mapped_column(Text)
    est_runtime_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    requires_gpu: Mapped[bool] = mapped_column(Boolean, default=False)
    min_vram_mb: Mapped[int] = mapped_column(Integer, default=0)
    max_cpu_pct: Mapped[int] = mapped_column(Integer, default=100)
    max_mem_mb: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    deadline_ts: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(String, default="queued")  # queued|running|done|canceled|failed
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    return_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    log_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


Index("ix_tasks_state", Task.state)


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    json_rules: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=False)


class ScheduleEvent(Base):
    __tablename__ = "schedule_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String)  # enqueued|started|finished|failed|canceled
    task_id: Mapped[str] = mapped_column(String, ForeignKey("tasks.id", ondelete="CASCADE"))
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Usage(Base):
    __tablename__ = "usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    provider: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    prompt_len: Mapped[int] = mapped_column(Integer, default=0)
    response_len: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
