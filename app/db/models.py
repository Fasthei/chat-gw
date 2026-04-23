from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Tool(Base):
    __tablename__ = "tools"
    __table_args__ = {"schema": "chat_gw"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    dispatcher: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    auth_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    secret_env_name: Mapped[str | None] = mapped_column(String(128))
    auth_header: Mapped[str | None] = mapped_column(String(128))
    auth_prefix: Mapped[str] = mapped_column(String(32), default="", nullable=False)

    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_schema: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    grants: Mapped[list[ToolRoleGrant]] = relationship(
        back_populates="tool", lazy="selectin", cascade="all, delete-orphan"
    )


class ToolRoleGrant(Base):
    __tablename__ = "tool_role_grants"
    __table_args__ = {"schema": "chat_gw"}

    tool_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chat_gw.tools.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(64), primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    granted_by: Mapped[str | None] = mapped_column(String(128))

    tool: Mapped[Tool] = relationship(back_populates="grants")


class ToolAuditLog(Base):
    __tablename__ = "tool_audit_log"
    __table_args__ = {"schema": "chat_gw"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_email: Mapped[str | None] = mapped_column(String(255))
    roles: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_id: Mapped[int | None] = mapped_column(BigInteger)
    arguments: Mapped[dict | None] = mapped_column(JSONB)
    sensitive_fields_hit: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    deny_reason: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[int | None] = mapped_column(Integer)
    error_kind: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
