from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.deps import get_current_user
from app.domain.models import APIError
from app.http.routes_public import DiagnosticSubmitIn, DiagnosticSubmitOut, detect_plan

router = APIRouter(prefix="/api/client", tags=["client"])


def _topic_from_flow(flow: str) -> str:
    f = (flow or "").strip().lower()
    if f == "alcohol_v1":
        return "alcohol"
    if f == "drugs_v1":
        return "drugs"
    if f == "points_v1":
        return "points"
    if f == "behavior_v1":
        return "incident"
    return "unknown"


@router.post("/diagnostic", response_model=DiagnosticSubmitOut)
def submit_diagnostic_client(
    payload: DiagnosticSubmitIn,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    repo = Repo(db)
    recommended_plan = detect_plan(payload)
    flow = (payload.flow or "").strip().lower()

    try:
        # ---- alcohol_v1 ----
        if flow == "alcohol_v1":
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

            row = repo.create_diagnostic_submission(
                user_id=user.id,
                reasons=["Алкоголь"],
                other_reason=None,
                situation=situation,
                history=history,
                goal=goal,
                recommended_plan=recommended_plan,
                meta_json={
                    "source": "client_diagnostic",
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

        # ---- drugs_v1 ----
        elif flow == "drugs_v1":
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

            row = repo.create_diagnostic_submission(
                user_id=user.id,
                reasons=["Наркотики"],
                other_reason=None,
                situation=situation,
                history=history,
                goal=goal,
                recommended_plan=recommended_plan,
                meta_json={
                    "source": "client_diagnostic",
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

        # ---- points_v1 ----
        elif flow == "points_v1":
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

            row = repo.create_diagnostic_submission(
                user_id=user.id,
                reasons=["Пункты / штрафы"],
                other_reason=None,
                situation=situation,
                history=history,
                goal=goal,
                recommended_plan=recommended_plan,
                meta_json={
                    "source": "client_diagnostic",
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

        # ---- behavior_v1 ----
        elif flow == "behavior_v1":
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

            row = repo.create_diagnostic_submission(
                user_id=user.id,
                reasons=["Поведение / инцидент"],
                other_reason=None,
                situation=situation,
                history=history,
                goal=goal,
                recommended_plan=recommended_plan,
                meta_json={
                    "source": "client_diagnostic",
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

        # ---- generic_v2 (legacy) ----
        elif flow == "generic_v2" or not flow:
            reasons = payload.reasons or []
            if not reasons:
                raise APIError("BAD_DIAGNOSTIC", "Generic flow requires reasons[]", status_code=422)

            row = repo.create_diagnostic_submission(
                user_id=user.id,
                reasons=[str(x).strip() for x in reasons if str(x).strip()],
                other_reason=(payload.other_reason or None),
                situation=(payload.situation or "").strip(),
                history=(payload.history or "").strip(),
                goal=(payload.goal or "").strip(),
                recommended_plan=recommended_plan,
                meta_json={
                    "source": "client_diagnostic",
                    "flow": "generic_v2",
                    "topic": (payload.topic or "Другое"),
                    "answers": {
                        "reasons": reasons,
                        "other_reason": payload.other_reason,
                        "situation": payload.situation,
                        "history": payload.history,
                        "goal": payload.goal,
                    },
                    "ip": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent"),
                },
            )

        else:
            raise APIError("BAD_DIAGNOSTIC", "Unsupported flow", {"flow": flow}, status_code=422)

        # Bind diagnostic to route_case (route + AI adapt instantly)
        topic_slug = _topic_from_flow(flow)
        case = repo.get_or_create_route_case(user.id, topic=topic_slug)
        case.topic = topic_slug

        if topic_slug != "unknown":
            case.setup_status = "complete"
            case.setup_step = 0
        else:
            if case.setup_status == "not_started":
                case.setup_status = "in_progress"

        answers = (row.meta_json or {}).get("answers") if hasattr(row, "meta_json") else None
        case.data_json = {
            "meta": {
                "topic": topic_slug,
                "diagnostic_flow": flow,
                "diagnostic_submission_id": str(row.id),
                "recommended_plan": recommended_plan,
            },
            "diagnostic": {"answers": answers or {}},
        }
        case.missing_json = {}

        db.commit()
        return DiagnosticSubmitOut(id=str(row.id), recommended_plan=row.recommended_plan)

    except APIError:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise exc


@router.get("/diagnostic/latest")
def latest_diagnostic(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    repo = Repo(db)
    row = repo.get_latest_diagnostic_submission_for_user(user.id)
    if not row:
        return {"data": None}

    return {
        "data": {
            "id": str(row.id),
            "reasons": row.reasons,
            "other_reason": row.other_reason,
            "situation": row.situation,
            "history": row.history,
            "goal": row.goal,
            "recommended_plan": row.recommended_plan,
            "meta_json": row.meta_json,
            "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else None,
        }
    }