from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import (
    JSON,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Role(str, Enum):
    user = "user"
    admin = "admin"
    consultant = "consultant"


class UserStatus(str, Enum):
    active = "active"
    blocked = "blocked"
    deleted = "deleted"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    locale: Mapped[str] = mapped_column(String(5), nullable=False, default="de")
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # IMPORTANT: enum type names must match migration: role / userstatus
    role: Mapped[Role] = mapped_column(SAEnum(Role, name="role"), nullable=False, default=Role.user)
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="userstatus"),
        nullable=False,
        default=UserStatus.active,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    orders: Mapped[list["Order"]] = relationship(back_populates="user", lazy="selectin")
    entitlements: Mapped[list["Entitlement"]] = relationship(back_populates="user", lazy="selectin")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_entity_created", "entity_type", "entity_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    title_de: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(ForeignKey("topics.id"), index=True, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    question_de: Mapped[str] = mapped_column(Text, nullable=False)
    question_en: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Rubric(Base):
    __tablename__ = "rubrics"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title_de: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    scale_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scale_max: Mapped[int] = mapped_column(Integer, nullable=False, default=5)


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(ForeignKey("topics.id"), index=True, nullable=False)
    title_de: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AISession(Base):
    __tablename__ = "ai_sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    locale: Mapped[str] = mapped_column(String(5), nullable=False, default="de")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIMessage(Base):
    __tablename__ = "ai_messages"
    __table_args__ = (Index("ix_ai_messages_session_created", "session_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("ai_sessions.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AIEvaluation(Base):
    __tablename__ = "ai_evaluations"
    __table_args__ = (Index("ix_ai_evals_session_created", "session_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("ai_sessions.id"), nullable=False)
    message_id: Mapped[UUID] = mapped_column(ForeignKey("ai_messages.id"), nullable=False)
    rubric_scores: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    summary_feedback: Mapped[str] = mapped_column(Text, nullable=False)
    detected_issues: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (Index("ix_slots_consultant_starts", "consultant_id", "starts_at_utc"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    consultant_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    starts_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    meeting_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    meeting_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("slot_id", name="uq_booking_slot_id"),
        Index("ix_bookings_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    slot_id: Mapped[UUID] = mapped_column(ForeignKey("slots.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="confirmed")
    client_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)




class DiagnosticSubmission(Base):
    __tablename__ = "diagnostic_submissions"
    __table_args__ = (Index("ix_diag_submission_created", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reasons: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    other_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    situation: Mapped[str] = mapped_column(Text, nullable=False)
    history: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_plan: Mapped[str] = mapped_column(String(32), nullable=False)
    meta_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

# --- Route / Case (Setup state machine) ---

class RouteCase(Base):
    __tablename__ = "route_cases"
    __table_args__ = (Index("ix_route_cases_user", "user_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # alcohol|drugs|points|incident|unknown
    topic: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")

    # not_started|in_progress|complete
    setup_status: Mapped[str] = mapped_column(String(16), nullable=False, default="not_started")
    setup_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    data_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    missing_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

class Product(Base):
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # ai_pack | booking | ...
    name_de: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    stripe_price_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)

    orders: Mapped[list["Order"]] = relationship(back_populates="product", lazy="selectin")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("provider", "provider_ref", name="uq_order_provider_ref"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="stripe")
    provider_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship(back_populates="orders", lazy="selectin")
    product: Mapped["Product"] = relationship(back_populates="orders", lazy="selectin")


class PaymentEvent(Base):
    __tablename__ = "payments_events"
    __table_args__ = (Index("ix_payment_events_processed", "processed_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="stripe")
    event_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Entitlement(Base):
    __tablename__ = "entitlements"
    __table_args__ = (Index("ix_entitlements_user_kind_valid", "user_id", "kind", "valid_to"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    qty_total: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    user: Mapped["User"] = relationship(back_populates="entitlements", lazy="selectin")
    order: Mapped["Order"] = relationship(lazy="selectin")

class RouteDay(Base):
    __tablename__ = "route_days"
    __table_args__ = (
        UniqueConstraint("user_id", "date_key", name="uq_route_days_user_date_key"),
        Index("ix_route_days_user_day", "user_id", "day_index"),
        Index("ix_route_days_user_date", "user_id", "date_key"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    date_key: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")

    tasks_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

# -----------------------------
# API error + DTO (Pydantic)
# -----------------------------
class APIError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None, status_code: int = 400):
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code
        super().__init__(message)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    name: str
    locale: str = "de"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SessionCreateIn(BaseModel):
    mode: str
    locale: str = "de"


class MessageIn(BaseModel):
    # Empty payload is allowed at schema level because API routes may convert
    # first-message empty posts into explicit boot commands ([[START_*]]).
    content: str = ""


class CheckoutIn(BaseModel):
    product_id: UUID


class CheckoutConfirmIn(BaseModel):
    checkout_session_id: str = Field(min_length=1)


class ErrorEnvelope(BaseModel):
    error: dict[str, Any]


class DataEnvelope(BaseModel):
    data: Any
