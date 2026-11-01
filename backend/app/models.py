"""ORM models. Schema changes go through Alembic (alembic/versions)."""

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex


class UTCDateTime(TypeDecorator[datetime]):
    """SQLite stores naive timestamps; normalise to aware UTC on both directions."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSON, list[Any]: JSON}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")  # "user" | "admin"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class AuthSession(Base):
    """Server-side login session; the cookie carries a random token, the DB only its hash."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship(lazy="joined")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class PasswordResetRequest(Base):
    __tablename__ = "password_reset_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|resolved
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str | None] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    request_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)


class Workspace(Base):
    """One uploaded payload and everything derived from it (sources, datasets, index, chat)."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    # scanned -> converting -> converted | failed
    status: Mapped[str] = mapped_column(String(16), default="scanned")
    upload_bytes: Mapped[int] = mapped_column(Integer, default=0)
    scan_notes: Mapped[list[Any]] = mapped_column(JSON, default=list)
    indexed_rows: Mapped[int] = mapped_column(Integer, default=0)
    indexed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    sources: Mapped[list["SourceFile"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", order_by="SourceFile.logical_path"
    )
    datasets: Mapped[list["Dataset"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", order_by="Dataset.name"
    )


class SourceFile(Base):
    """A file discovered inside the upload (XML, CSV or XLSX)."""

    __tablename__ = "source_files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    logical_path: Mapped[str] = mapped_column(Text)  # zip chain + member path, for humans
    filename: Mapped[str] = mapped_column(String(255))
    group: Mapped[str] = mapped_column(String(16), index=True)
    file_type: Mapped[str] = mapped_column(String(8))  # xml | csv | xlsx
    size: Mapped[int] = mapped_column(Integer)
    stored_name: Mapped[str] = mapped_column(String(128))  # relative to workspace/sources
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)

    workspace: Mapped[Workspace] = relationship(back_populates="sources")


class Dataset(Base):
    """A tabular CSV produced by conversion (or copied through) and editable by the owner."""

    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_files.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255))  # e.g. AR_PAYMENT_TERMS.CSV
    group: Mapped[str] = mapped_column(String(16), index=True)
    logical_path: Mapped[str] = mapped_column(Text, default="")
    record_tag: Mapped[str | None] = mapped_column(String(128))
    rows: Mapped[int] = mapped_column(Integer, default=0)
    columns: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    stored_name: Mapped[str] = mapped_column(String(128))  # relative to workspace/datasets
    edited: Mapped[bool] = mapped_column(Boolean, default=False)

    workspace: Mapped[Workspace] = relationship(back_populates="datasets")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # convert | index | compare
    subject_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default="queued"
    )  # queued|running|succeeded|failed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Comparison(Base):
    __tablename__ = "comparisons"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    left_workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    right_workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    items: Mapped[list["ComparisonItem"]] = relationship(
        cascade="all, delete-orphan", order_by="ComparisonItem.group"
    )


class ComparisonItem(Base):
    __tablename__ = "comparison_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    comparison_id: Mapped[str] = mapped_column(
        ForeignKey("comparisons.id", ondelete="CASCADE"), index=True
    )
    group: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))  # SAME|MODIFIED|ADDED|REMOVED
    left_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL")
    )
    right_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL")
    )
    rows_left: Mapped[int] = mapped_column(Integer, default=0)
    rows_right: Mapped[int] = mapped_column(Integer, default=0)
    added: Mapped[int] = mapped_column(Integer, default=0)
    removed: Mapped[int] = mapped_column(Integer, default=0)
    modified: Mapped[int] = mapped_column(Integer, default=0)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[Any]] = mapped_column(JSON, default=list)
    mode: Mapped[str | None] = mapped_column(String(16))  # llm | retrieval
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
