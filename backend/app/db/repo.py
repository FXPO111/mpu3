from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select, func, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.models import (
    AIEvaluation,
    AIMessage,
    AISession,
    Booking,
    DiagnosticSubmission,
    Entitlement,
    Order,
    PaymentEvent,
    Product,
    Slot,
    User,
    RouteCase,
    RouteDay,
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Repo:
    def __init__(self, db: Session):
        self.db = db

    # -----------------------------
    # Users
    # -----------------------------
    def create_user(self, email: str, password_hash: str, name: str, locale: str = "de") -> User:
        user = User(email=email.lower(), password_hash=password_hash, name=name, locale=locale)
        self.db.add(user)
        self.db.flush()
        return user

    def get_user_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email.lower()))

    # -----------------------------
    # AI Sessions / Messages / Eval
    # -----------------------------
    def create_ai_session(self, user_id: UUID, mode: str, locale: str) -> AISession:
        sess = AISession(user_id=user_id, mode=mode, locale=locale)
        self.db.add(sess)
        self.db.flush()
        return sess

    def get_ai_session(self, session_id: UUID) -> AISession | None:
        return self.db.get(AISession, session_id)

    def add_message(self, session_id: UUID, role: str, content: str) -> AIMessage:
        message = AIMessage(session_id=session_id, role=role, content=content)
        self.db.add(message)
        self.db.flush()
        return message

    def list_messages(self, session_id: UUID) -> list[AIMessage]:
        return list(
            self.db.scalars(
                select(AIMessage).where(AIMessage.session_id == session_id).order_by(AIMessage.created_at)
            ).all()
        )

    def add_evaluation(
        self,
        session_id: UUID,
        message_id: UUID,
        rubric_scores: dict,
        summary_feedback: str,
        detected_issues: dict,
    ) -> AIEvaluation:
        row = AIEvaluation(
            session_id=session_id,
            message_id=message_id,
            rubric_scores=rubric_scores,
            summary_feedback=summary_feedback,
            detected_issues=detected_issues,
        )
        self.db.add(row)
        return row

    def get_latest_diagnostic_submission_for_user(self, user_id: UUID) -> DiagnosticSubmission | None:
        return self.db.scalar(
            select(DiagnosticSubmission)
            .where(DiagnosticSubmission.user_id == user_id)
            .order_by(DiagnosticSubmission.created_at.desc())
            .limit(1)
        )

    # -----------------------------
    # Entitlements
    # -----------------------------
    def consume_entitlement(self, user_id: UUID, kind: str) -> bool:
        """
        Atomically consumes 1 unit from the earliest expiring entitlement of this kind.
        Filters expired and not-yet-valid entitlements.
        """
        now = _now_utc()

        ent = self.db.scalar(
            select(Entitlement)
            .where(
                Entitlement.user_id == user_id,
                Entitlement.kind == kind,
                Entitlement.qty_used < Entitlement.qty_total,
                Entitlement.valid_from <= now,
                or_(Entitlement.valid_to.is_(None), Entitlement.valid_to >= now),
            )
            # expiring first; unlimited last
            .order_by(Entitlement.valid_to.is_(None), Entitlement.valid_to, Entitlement.created_at)
            .with_for_update(of=Entitlement)
        )
        if not ent:
            return False

        ent.qty_used += 1
        return True

    def consume_credit(self, user_id: UUID) -> bool:
        return self.consume_entitlement(user_id, "ai_credits")

    def has_active_entitlement(self, user_id: UUID, kind: str) -> bool:
        now = _now_utc()
        row = self.db.scalar(
            select(Entitlement.id).where(
                Entitlement.user_id == user_id,
                Entitlement.kind == kind,
                Entitlement.valid_from <= now,
                or_(Entitlement.valid_to.is_(None), Entitlement.valid_to >= now),
            )
        )
        return row is not None

    def latest_paid_program_order(self, user_id: UUID) -> Order | None:
        return self.db.scalar(
            select(Order)
            .join(Product, Product.id == Order.product_id)
            .where(
                Order.user_id == user_id,
                Order.status == "paid",
                Product.type == "program",
            )
            .order_by(Order.updated_at.desc(), Order.created_at.desc())
            .limit(1)
        )

    def active_program_valid_to(self, user_id: UUID) -> datetime | None:
        now = _now_utc()
        return self.db.scalar(
            select(func.max(Entitlement.valid_to)).where(
                Entitlement.user_id == user_id,
                Entitlement.kind == "program_access",
                Entitlement.valid_from <= now,
                or_(Entitlement.valid_to.is_(None), Entitlement.valid_to >= now),
            )
        )

    def get_latest_diagnostic_submission_for_user(self, user_id: UUID) -> DiagnosticSubmission | None:
        return self.db.scalar(
            select(DiagnosticSubmission)
            .where(DiagnosticSubmission.user_id == user_id)
            .order_by(desc(DiagnosticSubmission.created_at))
            .limit(1)
        )

    def ai_credits_remaining(self, user_id: UUID) -> int:
        now = _now_utc()
        remaining = self.db.scalar(
            select(func.coalesce(func.sum(Entitlement.qty_total - Entitlement.qty_used), 0)).where(
                Entitlement.user_id == user_id,
                Entitlement.kind == "ai_credits",
                Entitlement.valid_from <= now,
                or_(Entitlement.valid_to.is_(None), Entitlement.valid_to >= now),
            )
        )
        return int(remaining or 0)

    def grant_entitlement_once(self, order: Order, kind: str, qty_total: int) -> Entitlement:
        existing = self.db.scalar(
            select(Entitlement).where(
                Entitlement.source_order_id == order.id,
                Entitlement.kind == kind,
            )
        )
        if existing:
            order.status = "paid"
            return existing

        ent = Entitlement(
            user_id=order.user_id,
            kind=kind,
            qty_total=qty_total,
            qty_used=0,
            valid_from=_now_utc(),
            source_order_id=order.id,
        )
        self.db.add(ent)
        order.status = "paid"
        return ent

    # -----------------------------
    # Slots / Bookings
    # -----------------------------
    def list_open_slots(self) -> list[Slot]:
        return list(self.db.scalars(select(Slot).where(Slot.status == "open").order_by(Slot.starts_at_utc)).all())

    def book_slot(self, user_id: UUID, slot_id: UUID) -> Booking:
        slot = self.db.get(Slot, slot_id, with_for_update=True)
        if not slot or slot.status != "open":
            raise ValueError("Slot not available")

        slot.status = "booked"
        booking = Booking(user_id=user_id, slot_id=slot_id, status="confirmed")
        self.db.add(booking)
        self.db.flush()
        return booking

    # -----------------------------
    # Products / Orders
    # -----------------------------
    def create_order(self, user_id: UUID, product: Product, provider_ref: str) -> Order:
        order = Order(
            user_id=user_id,
            product_id=product.id,
            amount_cents=product.price_cents,
            currency=product.currency,
            provider_ref=provider_ref,
            status="pending",
        )
        self.db.add(order)
        self.db.flush()
        return order

    def get_product(self, product_id: UUID) -> Product | None:
        return self.db.get(Product, product_id)

    def get_product_by_code(self, code: str) -> Product | None:
        return self.db.scalar(select(Product).where(Product.code == code, Product.active.is_(True)))

    def list_products(self) -> list[Product]:
        return list(self.db.scalars(select(Product).where(Product.active.is_(True))).all())

    def create_diagnostic_submission(
        self,
        reasons: list[str],
        situation: str,
        history: str,
        goal: str,
        recommended_plan: str,
        other_reason: str | None = None,
        user_id: UUID | None = None,
        meta_json: dict | None = None,
    ) -> DiagnosticSubmission:
        row = DiagnosticSubmission(
            user_id=user_id,
            reasons=reasons,
            other_reason=other_reason,
            situation=situation,
            history=history,
            goal=goal,
            recommended_plan=recommended_plan,
            meta_json=meta_json or {},
        )
        self.db.add(row)
        self.db.flush()
        return row

    # -----------------------------
    # Route Days
    # -----------------------------
    def get_route_day_by_date(self, user_id: UUID, date_key: str) -> RouteDay | None:
        return self.db.scalar(select(RouteDay).where(RouteDay.user_id == user_id, RouteDay.date_key == date_key))

    def get_max_route_day_index(self, user_id: UUID) -> int:
        v = self.db.scalar(select(func.max(RouteDay.day_index)).where(RouteDay.user_id == user_id))
        return int(v or 0)

    def create_route_day(self, user_id: UUID, date_key: str, day_index: int, tasks_json: list[dict]) -> RouteDay:
        row = RouteDay(
            user_id=user_id,
            date_key=date_key,
            day_index=day_index,
            status="open",
            tasks_json=tasks_json,
        )
        self.db.add(row)
        self.db.flush()
        return row

    # -----------------------------
    # Route Case (Setup)
    # -----------------------------
    def get_route_case(self, user_id: UUID) -> RouteCase | None:
        return self.db.scalar(select(RouteCase).where(RouteCase.user_id == user_id))

    def get_or_create_route_case(self, user_id: UUID, *, topic: str = "unknown") -> RouteCase:
        row = self.get_route_case(user_id)
        if row:
            return row
        row = RouteCase(user_id=user_id, topic=topic, setup_status="not_started", setup_step=0, data_json={}, missing_json={})
        self.db.add(row)
        self.db.flush()
        return row

    def get_diagnostic_submission(self, submission_id: UUID) -> DiagnosticSubmission | None:
        return self.db.get(DiagnosticSubmission, submission_id)

    def find_order_by_provider_ref(self, provider_ref: str) -> Order | None:
        return self.db.scalar(select(Order).where(Order.provider_ref == provider_ref))

    # -----------------------------
    # Payment Events (webhook idempotency)
    # -----------------------------
    def insert_payment_event(
        self,
        provider: str,
        event_id: str,
        event_type: str,
        payload: dict,
    ) -> tuple[PaymentEvent, bool]:
        """
        Race-safe insert:
          - If exists -> (existing, False)
          - Else try insert; on unique violation -> load existing and return (existing, False)
        """
        existing = self.db.scalar(select(PaymentEvent).where(PaymentEvent.event_id == event_id))
        if existing:
            return existing, False

        evt = PaymentEvent(provider=provider, event_id=event_id, type=event_type, payload_json=payload)
        self.db.add(evt)

        try:
            self.db.flush()
            return evt, True
        except IntegrityError:
            # Another worker inserted the same event_id first
            self.db.rollback()
            existing2 = self.db.scalar(select(PaymentEvent).where(PaymentEvent.event_id == event_id))
            if existing2:
                return existing2, False
            raise

    def mark_payment_event_processed(self, evt: PaymentEvent) -> None:
        evt.processed_at = _now_utc()