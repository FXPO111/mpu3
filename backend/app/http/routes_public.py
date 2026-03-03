from secrets import token_urlsafe
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.domain.models import APIError
from app.integrations.llm_openai import generate_therapy_reply
from app.integrations.payments_stripe import StripeError, create_checkout_session, is_stripe_configured
from app.security.auth import hash_password
from app.settings import settings

router = APIRouter(prefix="/api/public", tags=["public"])

PLAN_TO_PRODUCT_CODE: dict[str, str] = {
    "start": "PLAN_START",
    "pro": "PLAN_PRO",
    "intensive": "PLAN_INTENSIVE",
}


ALCOHOL_PROMILLE_BUCKETS = (
    "До 0.8‰",
    "0.8–1.59‰",
    "1.6‰ и выше",
    "Не знаю / нет под рукой",
)

ALCOHOL_MPU_REASONS = (
    "Был(а) за рулём после алкоголя",
    "ДТП / инцидент",
    "Повторное нарушение",
    "Другое",
)

ALCOHOL_FREQUENCY = (
    "Реже 1 раза в неделю",
    "1–2 раза в неделю",
    "3–5+ раз в неделю",
    "В основном по выходным",
)

ALCOHOL_LAST_TIME = (
    "В последние 7 дней",
    "В последний месяц",
    "1–3 месяца назад",
    "Более 3 месяцев назад",
)

# --- Drugs ---
DRUGS_SUBSTANCE = (
    "Каннабис (THC)",
    "Амфетамины / MDMA",
    "Кокаин",
    "Другое",
)

DRUGS_BASIS = (
    "Положительный тест (кровь/моча)",
    "Отказ от теста",
    "Хранение / обнаружение веществ",
    "Не знаю / нет документов",
)

DRUGS_FREQUENCY = (
    "Разово / эксперимент",
    "Редко (реже 1 раза в месяц)",
    "Иногда (1–3 раза в месяц)",
    "Регулярно (еженедельно+)",
)

DRUGS_LAST = (
    "В последние 7 дней",
    "В последний месяц",
    "1–3 месяца назад",
    "Более 3 месяцев назад",
)

# --- Points / fines ---
POINTS_BUCKET = (
    "1–3 пункта",
    "4–5 пунктов",
    "6–7 пунктов",
    "8+ / лишение прав",
)

POINTS_REASON = (
    "Скорость",
    "Красный / приоритет / опасный манёвр",
    "Телефон / отвлечение",
    "Другое",
)

POINTS_FREQUENCY = (
    "Единично",
    "2–3 раза в год",
    "Регулярно",
    "Много за короткий период",
)

POINTS_LAST = (
    "В последние 7 дней",
    "В последний месяц",
    "1–3 месяца назад",
    "Более 3 месяцев назад",
)

# --- Behavior / incident ---
INCIDENT_TYPE = (
    "Агрессия / конфликт на дороге",
    "Опасное вождение / экстремальная скорость",
    "ДТП по вине (без алкоголя/наркотиков)",
    "Другое",
)

INCIDENT_SEVERITY = (
    "Без ДТП, только остановка/штраф",
    "Инцидент без травм (мелкий ущерб)",
    "ДТП с травмами / крупный ущерб",
    "Суд/уголовное дело/испытательный срок",
)

INCIDENT_PATTERN = (
    "Единичный случай",
    "Повторялось несколько раз",
    "Постоянный стиль риска/импульсивность",
    "Не уверен(а)",
)

INCIDENT_LAST = (
    "В последние 7 дней",
    "В последний месяц",
    "1–3 месяца назад",
    "Более 3 месяцев назад",
)

class DiagnosticSubmitIn(BaseModel):
    # Backward compatible: old clients may omit `flow`.
    flow: str | None = Field(default=None, max_length=32)

    # Generic (legacy) flow fields
    reasons: list[str] | None = None
    other_reason: str | None = Field(default=None, max_length=120)
    situation: str | None = Field(default=None, max_length=2000)
    history: str | None = Field(default=None, max_length=2000)
    goal: str | None = Field(default=None, max_length=2000)

    # Alcohol v1 flow fields
    topic: str | None = Field(default=None, max_length=64)
    promille_bucket: str | None = Field(default=None, max_length=64)
    mpu_reason: str | None = Field(default=None, max_length=64)
    mpu_other: str | None = Field(default=None, max_length=60)
    drink_frequency: str | None = Field(default=None, max_length=64)
    last_drink: str | None = Field(default=None, max_length=64)

    # drugs_v1
    drug_substance: str | None = Field(default=None, max_length=64)
    drug_other: str | None = Field(default=None, max_length=60)
    drug_basis: str | None = Field(default=None, max_length=64)
    drug_frequency: str | None = Field(default=None, max_length=64)
    drug_last_use: str | None = Field(default=None, max_length=64)

    # points_v1
    points_bucket: str | None = Field(default=None, max_length=64)
    points_reason: str | None = Field(default=None, max_length=64)
    points_other: str | None = Field(default=None, max_length=60)
    points_frequency: str | None = Field(default=None, max_length=64)
    points_last: str | None = Field(default=None, max_length=64)

    # behavior_v1
    incident_type: str | None = Field(default=None, max_length=64)
    incident_other: str | None = Field(default=None, max_length=60)
    incident_severity: str | None = Field(default=None, max_length=64)
    incident_pattern: str | None = Field(default=None, max_length=64)
    incident_last: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _validate(self):
        flow = (self.flow or "").strip().lower()

        # ---------- alcohol_v1 ----------
        if flow == "alcohol_v1":
            if (self.topic or "").strip() != "Алкоголь":
                raise APIError("BAD_DIAGNOSTIC", "Alcohol flow requires topic=Алкоголь", status_code=422)
            if (self.promille_bucket or "").strip() not in ALCOHOL_PROMILLE_BUCKETS:
                raise APIError("BAD_DIAGNOSTIC", "Invalid promille_bucket", {"allowed": list(ALCOHOL_PROMILLE_BUCKETS)},
                               422)
            if (self.mpu_reason or "").strip() not in ALCOHOL_MPU_REASONS:
                raise APIError("BAD_DIAGNOSTIC", "Invalid mpu_reason", {"allowed": list(ALCOHOL_MPU_REASONS)}, 422)
            if (self.drink_frequency or "").strip() not in ALCOHOL_FREQUENCY:
                raise APIError("BAD_DIAGNOSTIC", "Invalid drink_frequency", {"allowed": list(ALCOHOL_FREQUENCY)}, 422)
            if (self.last_drink or "").strip() not in ALCOHOL_LAST_TIME:
                raise APIError("BAD_DIAGNOSTIC", "Invalid last_drink", {"allowed": list(ALCOHOL_LAST_TIME)}, 422)

            if (self.mpu_reason or "").strip() == "Другое":
                if not (self.mpu_other or "").strip() or len((self.mpu_other or "").strip()) > 60:
                    raise APIError("BAD_DIAGNOSTIC", "mpu_other required for 'Другое' (<=60)", status_code=422)
                self.mpu_other = (self.mpu_other or "").strip()
            else:
                self.mpu_other = None

            return self

            # ---------- drugs_v1 ----------
        if flow == "drugs_v1":
            if (self.topic or "").strip() != "Наркотики":
                raise APIError("BAD_DIAGNOSTIC", "Drugs flow requires topic=Наркотики", status_code=422)
            if (self.drug_substance or "").strip() not in DRUGS_SUBSTANCE:
                raise APIError("BAD_DIAGNOSTIC", "Invalid drug_substance", {"allowed": list(DRUGS_SUBSTANCE)}, 422)
            if (self.drug_basis or "").strip() not in DRUGS_BASIS:
                raise APIError("BAD_DIAGNOSTIC", "Invalid drug_basis", {"allowed": list(DRUGS_BASIS)}, 422)
            if (self.drug_frequency or "").strip() not in DRUGS_FREQUENCY:
                raise APIError("BAD_DIAGNOSTIC", "Invalid drug_frequency", {"allowed": list(DRUGS_FREQUENCY)}, 422)
            if (self.drug_last_use or "").strip() not in DRUGS_LAST:
                raise APIError("BAD_DIAGNOSTIC", "Invalid drug_last_use", {"allowed": list(DRUGS_LAST)}, 422)

            if (self.drug_substance or "").strip() == "Другое":
                if not (self.drug_other or "").strip() or len((self.drug_other or "").strip()) > 60:
                    raise APIError("BAD_DIAGNOSTIC", "drug_other required for 'Другое' (<=60)", status_code=422)
                self.drug_other = (self.drug_other or "").strip()
            else:
                self.drug_other = None
            return self

            # ---------- points_v1 ----------
        if flow == "points_v1":
            if (self.topic or "").strip() != "Пункты / штрафы":
                raise APIError("BAD_DIAGNOSTIC", "Points flow requires topic=Пункты / штрафы", status_code=422)
            if (self.points_bucket or "").strip() not in POINTS_BUCKET:
                raise APIError("BAD_DIAGNOSTIC", "Invalid points_bucket", {"allowed": list(POINTS_BUCKET)}, 422)
            if (self.points_reason or "").strip() not in POINTS_REASON:
                raise APIError("BAD_DIAGNOSTIC", "Invalid points_reason", {"allowed": list(POINTS_REASON)}, 422)
            if (self.points_frequency or "").strip() not in POINTS_FREQUENCY:
                raise APIError("BAD_DIAGNOSTIC", "Invalid points_frequency", {"allowed": list(POINTS_FREQUENCY)}, 422)
            if (self.points_last or "").strip() not in POINTS_LAST:
                raise APIError("BAD_DIAGNOSTIC", "Invalid points_last", {"allowed": list(POINTS_LAST)}, 422)

            if (self.points_reason or "").strip() == "Другое":
                if not (self.points_other or "").strip() or len((self.points_other or "").strip()) > 60:
                    raise APIError("BAD_DIAGNOSTIC", "points_other required for 'Другое' (<=60)", status_code=422)
                self.points_other = (self.points_other or "").strip()
            else:
                self.points_other = None
            return self

            # ---------- behavior_v1 ----------
        if flow == "behavior_v1":
            if (self.topic or "").strip() != "Поведение / инцидент":
                raise APIError("BAD_DIAGNOSTIC", "Behavior flow requires topic=Поведение / инцидент", status_code=422)
            if (self.incident_type or "").strip() not in INCIDENT_TYPE:
                raise APIError("BAD_DIAGNOSTIC", "Invalid incident_type", {"allowed": list(INCIDENT_TYPE)}, 422)
            if (self.incident_severity or "").strip() not in INCIDENT_SEVERITY:
                raise APIError("BAD_DIAGNOSTIC", "Invalid incident_severity", {"allowed": list(INCIDENT_SEVERITY)}, 422)
            if (self.incident_pattern or "").strip() not in INCIDENT_PATTERN:
                raise APIError("BAD_DIAGNOSTIC", "Invalid incident_pattern", {"allowed": list(INCIDENT_PATTERN)}, 422)
            if (self.incident_last or "").strip() not in INCIDENT_LAST:
                raise APIError("BAD_DIAGNOSTIC", "Invalid incident_last", {"allowed": list(INCIDENT_LAST)}, 422)

            if (self.incident_type or "").strip() == "Другое":
                if not (self.incident_other or "").strip() or len((self.incident_other or "").strip()) > 60:
                    raise APIError("BAD_DIAGNOSTIC", "incident_other required for 'Другое' (<=60)", status_code=422)
                self.incident_other = (self.incident_other or "").strip()
            else:
                self.incident_other = None
            return self

            # ---------- generic_v2 ----------
        self.flow = "generic_v2"
        if not self.reasons or not isinstance(self.reasons, list):
            raise APIError("BAD_DIAGNOSTIC", "reasons is required", status_code=422)
        if len(self.reasons) < 1 or len(self.reasons) > 2:
            raise APIError("BAD_DIAGNOSTIC", "reasons must have 1-2 items", status_code=422)
        if "Другое" in self.reasons:
            if not (self.other_reason or "").strip() or len((self.other_reason or "").strip()) > 120:
                raise APIError("BAD_DIAGNOSTIC", "other_reason required when 'Другое' selected", status_code=422)
            self.other_reason = (self.other_reason or "").strip()

        if not (self.situation or "").strip() or len((self.situation or "").strip()) < 12:
            raise APIError("BAD_DIAGNOSTIC", "situation must be at least 12 chars", status_code=422)
        if not (self.history or "").strip() or len((self.history or "").strip()) < 12:
            raise APIError("BAD_DIAGNOSTIC", "history must be at least 12 chars", status_code=422)
        if not (self.goal or "").strip() or len((self.goal or "").strip()) < 8:
            raise APIError("BAD_DIAGNOSTIC", "goal must be at least 8 chars", status_code=422)

        self.situation = (self.situation or "").strip()
        self.history = (self.history or "").strip()
        self.goal = (self.goal or "").strip()
        return self


class DiagnosticSubmitOut(BaseModel):
    id: str
    recommended_plan: str


class PublicCheckoutIn(BaseModel):
    plan: Literal["start", "pro", "intensive"]
    email: str = Field(min_length=5, max_length=320)
    name: str | None = Field(default=None, max_length=120)
    success_url: str | None = Field(default=None, max_length=2000)
    cancel_url: str | None = Field(default=None, max_length=2000)


class PublicCheckoutOut(BaseModel):
    order_id: str
    checkout_session_id: str
    checkout_url: str | None


class PublicTherapyHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class PublicTherapyReplyIn(BaseModel):
    message: str = Field(min_length=2, max_length=8000)
    diagnostic_submission_id: str | None = Field(default=None)
    locale: str = Field(default="ru", max_length=5)
    history: list[PublicTherapyHistoryItem] = Field(default_factory=list, max_length=30)


class PublicTherapyReplyOut(BaseModel):
    reply: str
    plan: str
    risk_level: str


def _detect_plan_generic(payload: DiagnosticSubmitIn) -> str:
    text = " ".join(
        (payload.reasons or [])
        + [payload.other_reason or "", payload.situation or "", payload.history or "", payload.goal or ""]
    ).lower()
    intense_keywords = ["повтор", "отказ", "сложно", "долго", "стресс", "срочно", "конфликт", "инцидент"]
    pro_keywords = ["документ", "план", "трениров", "ошиб", "формулиров", "подготов"]

    if any(k in text for k in intense_keywords):
        return "intensive"
    if any(k in text for k in pro_keywords):
        return "pro"
    return "start"


def _detect_plan_alcohol(payload: DiagnosticSubmitIn) -> str:
    promille = (payload.promille_bucket or "").strip()
    reason = (payload.mpu_reason or "").strip()
    freq = (payload.drink_frequency or "").strip()
    last = (payload.last_drink or "").strip()

    # Hard rules first (risk + complexity)
    if reason == "Повторное нарушение":
        return "intensive"
    if promille == "1.6‰ и выше":
        return "intensive"

    promille_score = {
        "До 0.8‰": 0,
        "0.8–1.59‰": 1,
        "1.6‰ и выше": 2,
        "Не знаю / нет под рукой": 1,
    }.get(promille, 1)
    reason_score = {
        "Был(а) за рулём после алкоголя": 1,
        "ДТП / инцидент": 2,
        "Повторное нарушение": 3,
        "Другое": 1,
    }.get(reason, 1)
    freq_score = {
        "Реже 1 раза в неделю": 0,
        "1–2 раза в неделю": 1,
        "3–5+ раз в неделю": 2,
        "В основном по выходным": 1,
    }.get(freq, 1)
    last_score = {
        "В последние 7 дней": 3,
        "В последний месяц": 2,
        "1–3 месяца назад": 1,
        "Более 3 месяцев назад": 0,
    }.get(last, 1)

    score = promille_score + reason_score + freq_score + last_score
    if score >= 6:
        return "intensive"
    if score >= 3:
        return "pro"
    return "start"

def _detect_plan_drugs(p: DiagnosticSubmitIn) -> str:
    substance = (p.drug_substance or "").strip()
    basis = (p.drug_basis or "").strip()
    freq = (p.drug_frequency or "").strip()
    last = (p.drug_last_use or "").strip()

    # hard
    if basis == "Отказ от теста":
        return "intensive"
    if freq == "Регулярно (еженедельно+)":
        return "intensive"
    if last == "В последние 7 дней":
        return "intensive"

    sub_score = {
        "Каннабис (THC)": 1,
        "Амфетамины / MDMA": 2,
        "Кокаин": 3,
        "Другое": 2,
    }.get(substance, 2)

    basis_score = {
        "Положительный тест (кровь/моча)": 2,
        "Отказ от теста": 3,
        "Хранение / обнаружение веществ": 2,
        "Не знаю / нет документов": 1,
    }.get(basis, 1)

    freq_score = {
        "Разово / эксперимент": 0,
        "Редко (реже 1 раза в месяц)": 1,
        "Иногда (1–3 раза в месяц)": 2,
        "Регулярно (еженедельно+)": 3,
    }.get(freq, 1)

    last_score = {
        "В последние 7 дней": 3,
        "В последний месяц": 2,
        "1–3 месяца назад": 1,
        "Более 3 месяцев назад": 0,
    }.get(last, 1)

    score = sub_score + basis_score + freq_score + last_score
    if score >= 8:
        return "intensive"
    if score >= 4:
        return "pro"
    return "start"


def _detect_plan_points(p: DiagnosticSubmitIn) -> str:
    bucket = (p.points_bucket or "").strip()
    reason = (p.points_reason or "").strip()
    freq = (p.points_frequency or "").strip()
    last = (p.points_last or "").strip()

    if bucket == "8+ / лишение прав":
        return "intensive"

    b = {"1–3 пункта": 0, "4–5 пунктов": 1, "6–7 пунктов": 2, "8+ / лишение прав": 3}.get(bucket, 1)
    r = {"Скорость": 1, "Красный / приоритет / опасный манёвр": 2, "Телефон / отвлечение": 1, "Другое": 1}.get(reason, 1)
    f = {"Единично": 0, "2–3 раза в год": 1, "Регулярно": 2, "Много за короткий период": 3}.get(freq, 1)
    l = {"В последние 7 дней": 3, "В последний месяц": 2, "1–3 месяца назад": 1, "Более 3 месяцев назад": 0}.get(last, 1)

    score = b + r + f + l
    if score >= 6:
        return "intensive"
    if score >= 3:
        return "pro"
    return "start"


def _detect_plan_behavior(p: DiagnosticSubmitIn) -> str:
    it = (p.incident_type or "").strip()
    sev = (p.incident_severity or "").strip()
    pat = (p.incident_pattern or "").strip()
    last = (p.incident_last or "").strip()

    if sev in ("ДТП с травмами / крупный ущерб", "Суд/уголовное дело/испытательный срок"):
        return "intensive"

    t = {
        "Агрессия / конфликт на дороге": 1,
        "Опасное вождение / экстремальная скорость": 2,
        "ДТП по вине (без алкоголя/наркотиков)": 2,
        "Другое": 1,
    }.get(it, 1)

    s = {
        "Без ДТП, только остановка/штраф": 1,
        "Инцидент без травм (мелкий ущерб)": 2,
        "ДТП с травмами / крупный ущерб": 3,
        "Суд/уголовное дело/испытательный срок": 3,
    }.get(sev, 2)

    ptn = {
        "Единичный случай": 0,
        "Повторялось несколько раз": 2,
        "Постоянный стиль риска/импульсивность": 3,
        "Не уверен(а)": 1,
    }.get(pat, 1)

    l = {"В последние 7 дней": 3, "В последний месяц": 2, "1–3 месяца назад": 1, "Более 3 месяцев назад": 0}.get(last, 1)

    score = t + s + ptn + l
    if score >= 7:
        return "intensive"
    if score >= 3:
        return "pro"
    return "start"


def detect_plan(payload: DiagnosticSubmitIn) -> str:
    flow = (payload.flow or "").strip().lower()
    if flow == "alcohol_v1":
        return _detect_plan_alcohol(payload)
    if flow == "drugs_v1":
        return _detect_plan_drugs(payload)
    if flow == "points_v1":
        return _detect_plan_points(payload)
    if flow == "behavior_v1":
        return _detect_plan_behavior(payload)
    return _detect_plan_generic(payload)


def _safe_redirect_url(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if not (candidate.startswith("http://") or candidate.startswith("https://")):
        raise APIError("BAD_REDIRECT_URL", "Redirect URL must be absolute http(s) URL", status_code=422)
    return candidate


def _normalize_locale(locale: str) -> str:
    loc = (locale or "ru").strip().lower()
    if loc.startswith("de"):
        return "de"
    if loc.startswith("en"):
        return "en"
    return "ru"


@router.get("/expert")
def expert():
    return {
        "data": {
            "bio": "Certified MPU consultant",
            "languages": ["de", "en"],
            "city_for_offline": "Berlin",
            "pricing_summary": "AI packs + paid consultation slots",
        }
    }


@router.get("/products")
def products(db: Session = Depends(get_db)):
    repo = Repo(db)
    rows = repo.list_products()
    return {
        "data": [
            {"id": str(p.id), "code": p.code, "price_cents": p.price_cents, "currency": p.currency, "type": p.type}
            for p in rows
        ]
    }


@router.get("/slots")
def slots(db: Session = Depends(get_db)):
    repo = Repo(db)
    rows = repo.list_open_slots()
    return {
        "data": [
            {
                "id": str(s.id),
                "starts_at_utc": s.starts_at_utc.isoformat(),
                "duration_min": s.duration_min,
                "title": s.title,
            }
            for s in rows
        ]
    }


@router.post("/diagnostic", response_model=DiagnosticSubmitOut)
def submit_diagnostic(payload: DiagnosticSubmitIn, request: Request, db: Session = Depends(get_db)):
    recommended_plan = detect_plan(payload)

    if (payload.flow or "").strip().lower() == "alcohol_v1":
        reason_label = (payload.mpu_reason or "").strip()
        if reason_label == "Другое":
            reason_label = f"Другое: {(payload.mpu_other or '').strip()}"

        situation = (
            "Алкоголь. "
            f"Промилле: {(payload.promille_bucket or '').strip()}; "
            f"Причина MPU: {reason_label}; "
            f"Частота: {(payload.drink_frequency or '').strip()}; "
            f"Последний раз: {(payload.last_drink or '').strip()}."
        )
        history = "Ответы собраны в корзины (risk buckets) для построения маршрута подготовки."
        goal = "Подготовка к MPU по алкоголю: ответственность, изменение поведения, устойчивый план и формулировки для интервью."

        row = Repo(db).create_diagnostic_submission(
            reasons=["Алкоголь"],
            other_reason=None,
            situation=situation,
            history=history,
            goal=goal,
            recommended_plan=recommended_plan,
            meta_json={
                "source": "public_diagnostic",
                "flow": "alcohol_v1",
                "topic": "Алкоголь",
                "answers": {
                    "promille_bucket": (payload.promille_bucket or "").strip(),
                    "mpu_reason": (payload.mpu_reason or "").strip(),
                    "mpu_other": (payload.mpu_other or None),
                    "drink_frequency": (payload.drink_frequency or "").strip(),
                    "last_drink": (payload.last_drink or "").strip(),
                },
                "ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )
        db.commit()
        return DiagnosticSubmitOut(id=str(row.id), recommended_plan=row.recommended_plan)

    if (payload.flow or "").strip().lower() == "drugs_v1":
        substance_label = (payload.drug_substance or "").strip()
        if substance_label == "Другое":
            substance_label = f"Другое: {(payload.drug_other or '').strip()}"

        situation = (
            "Наркотики. "
            f"Вещество: {substance_label}; "
            f"Основание: {(payload.drug_basis or '').strip()}; "
            f"Частота: {(payload.drug_frequency or '').strip()}; "
            f"Последний раз: {(payload.drug_last_use or '').strip()}."
        )
        history = "Ответы собраны корзинами (risk buckets) для построения маршрута подготовки."
        goal = "Подготовка к MPU по наркотикам: ответственность, отказ/изменение поведения, доказательная база, формулировки интервью."

        row = Repo(db).create_diagnostic_submission(
            reasons=["Наркотики"],
            other_reason=None,
            situation=situation,
            history=history,
            goal=goal,
            recommended_plan=recommended_plan,
            meta_json={
                "source": "public_diagnostic",
                "flow": "drugs_v1",
                "topic": "Наркотики",
                "answers": {
                    "drug_substance": (payload.drug_substance or "").strip(),
                    "drug_other": payload.drug_other or None,
                    "drug_basis": (payload.drug_basis or "").strip(),
                    "drug_frequency": (payload.drug_frequency or "").strip(),
                    "drug_last_use": (payload.drug_last_use or "").strip(),
                },
                "ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )
        db.commit()
        return DiagnosticSubmitOut(id=str(row.id), recommended_plan=row.recommended_plan)

    if (payload.flow or "").strip().lower() == "points_v1":
        reason_label = (payload.points_reason or "").strip()
        if reason_label == "Другое":
            reason_label = f"Другое: {(payload.points_other or '').strip()}"

        situation = (
            "Пункты/штрафы. "
            f"Пункты: {(payload.points_bucket or '').strip()}; "
            f"Причина: {reason_label}; "
            f"Частота: {(payload.points_frequency or '').strip()}; "
            f"Последний раз: {(payload.points_last or '').strip()}."
        )
        history = "Ответы собраны корзинами (risk buckets) для построения маршрута подготовки."
        goal = "Подготовка к MPU по пунктам: анализ причин, устойчивые изменения, стратегия предотвращения повторов, формулировки интервью."

        row = Repo(db).create_diagnostic_submission(
            reasons=["Пункты / штрафы"],
            other_reason=None,
            situation=situation,
            history=history,
            goal=goal,
            recommended_plan=recommended_plan,
            meta_json={
                "source": "public_diagnostic",
                "flow": "points_v1",
                "topic": "Пункты / штрафы",
                "answers": {
                    "points_bucket": (payload.points_bucket or "").strip(),
                    "points_reason": (payload.points_reason or "").strip(),
                    "points_other": payload.points_other or None,
                    "points_frequency": (payload.points_frequency or "").strip(),
                    "points_last": (payload.points_last or "").strip(),
                },
                "ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )
        db.commit()
        return DiagnosticSubmitOut(id=str(row.id), recommended_plan=row.recommended_plan)

    if (payload.flow or "").strip().lower() == "behavior_v1":
        type_label = (payload.incident_type or "").strip()
        if type_label == "Другое":
            type_label = f"Другое: {(payload.incident_other or '').strip()}"

        situation = (
            "Поведение/инцидент. "
            f"Тип: {type_label}; "
            f"Тяжесть: {(payload.incident_severity or '').strip()}; "
            f"Паттерн: {(payload.incident_pattern or '').strip()}; "
            f"Последний раз: {(payload.incident_last or '').strip()}."
        )
        history = "Ответы собраны корзинами (risk buckets) для построения маршрута подготовки."
        goal = "Подготовка к MPU по поведению: ответственность, триггеры, самоконтроль, безопасные стратегии, формулировки интервью."

        row = Repo(db).create_diagnostic_submission(
            reasons=["Поведение / инцидент"],
            other_reason=None,
            situation=situation,
            history=history,
            goal=goal,
            recommended_plan=recommended_plan,
            meta_json={
                "source": "public_diagnostic",
                "flow": "behavior_v1",
                "topic": "Поведение / инцидент",
                "answers": {
                    "incident_type": (payload.incident_type or "").strip(),
                    "incident_other": payload.incident_other or None,
                    "incident_severity": (payload.incident_severity or "").strip(),
                    "incident_pattern": (payload.incident_pattern or "").strip(),
                    "incident_last": (payload.incident_last or "").strip(),
                },
                "ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )
        db.commit()
        return DiagnosticSubmitOut(id=str(row.id), recommended_plan=row.recommended_plan)

@router.post("/therapy/reply", response_model=PublicTherapyReplyOut)
def public_therapy_reply(payload: PublicTherapyReplyIn, db: Session = Depends(get_db)):
    repo = Repo(db)

    diagnostic_context: dict[str, str | list[str]] = {
        "reasons": [],
        "goal": "",
        "situation": "",
        "history": "",
        "focus": ["Стабилизация", "Осознанность", "Ответственное поведение"],
    }
    plan = "start"
    risk_level = "moderate"

    if payload.diagnostic_submission_id:
        diag = None
        try:
            diag_id = UUID(payload.diagnostic_submission_id)
            diag = repo.get_diagnostic_submission(diag_id)
        except ValueError:
            diag = None

        if diag:
            meta = diag.meta_json or {}
            flow = str(meta.get("flow") or "").strip().lower()

            if flow == "alcohol_v1":
                answers = (meta.get("answers") or {}) if isinstance(meta.get("answers"), dict) else {}
                reason_label = str(answers.get("mpu_reason") or "").strip() or "Алкоголь"
                if reason_label == "Другое":
                    other = str(answers.get("mpu_other") or "").strip()
                    if other:
                        reason_label = f"Другое: {other}"

                diagnostic_context = {
                    "reasons": ["Алкоголь"],
                    "goal": diag.goal,
                    "situation": diag.situation,
                    "history": diag.history,
                    "alcohol": {
                        "promille_bucket": str(answers.get("promille_bucket") or "").strip(),
                        "mpu_reason": str(answers.get("mpu_reason") or "").strip(),
                        "mpu_other": str(answers.get("mpu_other") or "").strip() or None,
                        "drink_frequency": str(answers.get("drink_frequency") or "").strip(),
                        "last_drink": str(answers.get("last_drink") or "").strip(),
                    },
                    "focus": [
                        f"Алкоголь — промилле: {str(answers.get('promille_bucket') or '').strip()}",
                        f"Причина MPU: {reason_label}",
                        f"Последний раз: {str(answers.get('last_drink') or '').strip()}",
                    ],
                }
            else:
                diagnostic_context = {
                    "reasons": diag.reasons,
                    "goal": diag.goal,
                    "situation": diag.situation,
                    "history": diag.history,
                    "focus": [
                        f"Триггер: {diag.reasons[0]}" if diag.reasons else "Стабилизация",
                        f"Цель: {diag.goal[:160]}",
                        "Снижение риска срыва",
                    ],
                }
            plan = diag.recommended_plan

            if flow == "alcohol_v1":
                last = ""
                try:
                    answers = (meta.get("answers") or {}) if isinstance(meta.get("answers"), dict) else {}
                    last = str(answers.get("last_drink") or "")
                except Exception:
                    last = ""
                risk_level = "high" if plan == "intensive" or (last.strip() in ("В последние 7 дней", "В последний месяц")) else "moderate"
            else:
                risk_level = "high" if len(diag.history or "") > 160 else "moderate"

    reply = generate_therapy_reply(
        locale=_normalize_locale(payload.locale),
        diagnostic_context=diagnostic_context,
        history=[m.model_dump() for m in payload.history],
        user_message=payload.message,
    )

    return PublicTherapyReplyOut(reply=reply, plan=plan, risk_level=risk_level)


@router.post("/checkout", response_model=PublicCheckoutOut)
def public_checkout(payload: PublicCheckoutIn, db: Session = Depends(get_db)):
    repo = Repo(db)
    product_code = PLAN_TO_PRODUCT_CODE[payload.plan]
    product = repo.get_product_by_code(product_code)
    if not product:
        raise APIError(
            "PRODUCT_NOT_FOUND",
            "Product is not configured",
            {"expected_codes": sorted(PLAN_TO_PRODUCT_CODE.values())},
            status_code=404,
        )

    if not is_stripe_configured(settings.stripe_secret_key):
        raise APIError("STRIPE_NOT_CONFIGURED", "Stripe keys are missing", status_code=503)

    user = repo.get_user_by_email(payload.email)
    if not user:
        name = (payload.name or payload.email.split("@")[0] or "Client")[:120]
        user = repo.create_user(
            email=payload.email,
            password_hash=hash_password(token_urlsafe(24)),
            name=name,
            locale="de",
        )

    order = repo.create_order(user.id, product, provider_ref=f"tmp_{token_urlsafe(18)}")
    order.provider = "stripe"
    order.status = "pending"

    try:
        session = create_checkout_session(
            secret_key=settings.stripe_secret_key,
            order_id=str(order.id),
            product_id=str(product.id),
            product_name=product.name_de,
            unit_amount_cents=product.price_cents,
            currency=product.currency,
            stripe_price_id=product.stripe_price_id,
            frontend_url=settings.frontend_url,
            customer_email=user.email,
            success_url_override=_safe_redirect_url(payload.success_url),
            cancel_url_override=_safe_redirect_url(payload.cancel_url),
        )
    except StripeError as exc:
        db.rollback()
        raise APIError("CHECKOUT_FAILED", "Stripe checkout failed", status_code=502) from exc

    order.provider_ref = session["id"]
    db.commit()

    return PublicCheckoutOut(
        order_id=str(order.id),
        checkout_session_id=session["id"],
        checkout_url=session.get("url"),
    )