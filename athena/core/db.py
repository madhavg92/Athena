"""Database layer (SQLAlchemy 2.0). SQLite locally, Postgres in production."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True), dict[str, Any]: JSON}


class Receipt(Base):
    __tablename__ = "receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    time: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(200))
    recipient: Mapped[str | None] = mapped_column(String(200))
    rule_id: Mapped[str | None] = mapped_column(String(20), index=True)
    action_type: Mapped[str] = mapped_column(String(20))
    delivery: Mapped[str | None] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(20))
    sources: Mapped[Any] = mapped_column(JSON, default=list)
    output: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    item_key: Mapped[str | None] = mapped_column(String(300), index=True)
    deliver_at: Mapped[datetime | None] = mapped_column(default=None)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(20), index=True)
    item_key: Mapped[str] = mapped_column(String(300), index=True)
    client: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(50))
    opened_at: Mapped[datetime] = mapped_column(default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(default=None)
    ladder_step: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[Any] = mapped_column(JSON, default=dict)
    sends_count: Mapped[Any] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(10), default="open", index=True)
    payload: Mapped[Any] = mapped_column(JSON, default=dict)


class DigestItem(Base):
    __tablename__ = "digest_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    user: Mapped[str] = mapped_column(String(200), index=True)
    rule_id: Mapped[str] = mapped_column(String(20))
    item_key: Mapped[str | None] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(default=None)


class QuestionLog(Base):
    __tablename__ = "question_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    time: Mapped[datetime] = mapped_column(default=utcnow)
    user: Mapped[str] = mapped_column(String(200), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    tools: Mapped[Any] = mapped_column(JSON, default=list)
    idk: Mapped[bool] = mapped_column(Boolean, default=False)
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


class Turn(Base):
    __tablename__ = "turns"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(200), index=True)
    user: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    time: Mapped[datetime] = mapped_column(default=utcnow)


class KillSwitch(Base):
    __tablename__ = "kill_switches"
    scope: Mapped[str] = mapped_column(String(10), primary_key=True)
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    on: Mapped[bool] = mapped_column(Boolean, default=True)
    set_by: Mapped[str] = mapped_column(String(200))
    set_at: Mapped[datetime] = mapped_column(default=utcnow)


class ReviewMark(Base):
    __tablename__ = "review_marks"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(Integer, index=True)
    reviewer: Mapped[str] = mapped_column(String(200))
    verdict: Mapped[str] = mapped_column(String(10))
    note: Mapped[str | None] = mapped_column(Text)
    time: Mapped[datetime] = mapped_column(default=utcnow)


class RuleState(Base):
    """Runtime state of a rule: phase override after demotion, staleness, last run."""

    __tablename__ = "rule_state"
    rule_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    phase: Mapped[int | None] = mapped_column(Integer, default=None)
    phase_reason: Mapped[str | None] = mapped_column(Text)
    phase_changed_at: Mapped[datetime | None] = mapped_column(default=None)
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_at: Mapped[datetime | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)


def database_url(url: str | None = None) -> str:
    """DATABASE_URL, default SQLite. `postgres://` and `postgresql://` use the psycopg 3 driver."""
    url = url or os.environ.get("DATABASE_URL", "sqlite:///athena.db")
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Database:
    def __init__(self, url: str | None = None) -> None:
        self.url = database_url(url)
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if self.url in ("sqlite://", "sqlite:///:memory:"):
            kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
        self.engine = create_engine(self.url, **kwargs)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)
        if self.engine.dialect.name == "sqlite":
            Base.metadata.create_all(self.engine)  # local convenience; Postgres uses Alembic

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._sessions() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite drops tz info; treat naive values as UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)
