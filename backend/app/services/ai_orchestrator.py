# ai_orchestrator.py
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.domain.models import APIError, AIMessage, Topic
from app.integrations.llm_openai import generate_assistant_reply, translate_question_to_ru, generate_free_question_reply
from app.services.question_bank import next_question
from app.services.scoring import evaluate_user_message
from dataclasses import dataclass, is_dataclass, replace as dc_replace


def _strip_machine_lines_for_client(s: str) -> str:
    """Remove machine-control lines from assistant content for UI display.

    IMPORTANT: this is ONLY for the response payload returned to the client.
    The DB-stored message keeps machine lines so server-side state can be recovered.
    """
    out: list[str] = []
    for line in (s or "").splitlines():
        t = line.strip()
        if t.startswith("[[DAY_PLAN]]"):
            continue
        if t.startswith("[[EVAL]]"):
            continue
        if t.startswith("[[COURSE]]"):
            continue
        if "[[DOSSIER_UPDATE]]" in t:
            continue
        out.append(line)
    return "\n".join(out).strip()


def _publicize_ai_message(db: Session, msg: Any) -> Any:
    """Return a safe-to-render copy of AIMessage without machine lines.

    This avoids leaking internal markers like [[COURSE]] into UI, while keeping
    the stored message intact for state recovery.
    """
    try:
        raw = getattr(msg, "content", None)
    except Exception:  # noqa: BLE001
        return msg

    if raw is None:
        return msg

    clean = _strip_machine_lines_for_client(str(raw))
    if clean == str(raw):
        return msg

    # Pydantic v2
    if hasattr(msg, "model_copy"):
        try:
            return msg.model_copy(update={"content": clean})
        except Exception:  # noqa: BLE001
            pass

    # Pydantic v1
    if hasattr(msg, "copy"):
        try:
            return msg.copy(update={"content": clean})
        except Exception:  # noqa: BLE001
            pass

    # dataclass
    if is_dataclass(msg):
        try:
            return dc_replace(msg, content=clean)
        except Exception:  # noqa: BLE001
            pass

    # SQLAlchemy ORM: detach then mutate so we don't persist the sanitized content
    if hasattr(msg, "_sa_instance_state"):
        try:
            db.expunge(msg)
            setattr(msg, "content", clean)
            return msg
        except Exception:  # noqa: BLE001
            return msg

    # Generic object: shallow clone if possible
    try:
        import copy

        cloned = copy.copy(msg)
        setattr(cloned, "content", clean)
        return cloned
    except Exception:  # noqa: BLE001
        return msg


def _extract_topic_id(db: Session, case) -> UUID | None:
    try:
        slug = (getattr(case, "topic", None) or "").strip().lower()
        if not slug:
            return None
        return db.scalar(select(Topic.id).where(Topic.slug == slug))
    except Exception:  # noqa: BLE001
        return None


def _build_diagnostic_summary(repo: Repo, user_id: UUID, locale: str) -> str | None:
    try:
        row = repo.get_latest_diagnostic_submission_for_user(user_id)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return None

    if not row:
        return None

    meta = getattr(row, "meta_json", None) or {}
    flow = str(meta.get("flow") or "").strip().lower()
    answers = meta.get("answers") or {}

    loc = (locale or "de").strip().lower()
    is_de = loc.startswith("de")
    is_ru = loc.startswith("ru")

    def label(de: str, ru: str) -> str:
        return de if is_de else (ru if is_ru else de)

    def g(key: str) -> str:
        v = answers.get(key)
        if v is None:
            return ""
        return str(v).strip()

    def is_other(value: str) -> bool:
        v = (value or "").strip().lower()
        return v in {"другое", "andere", "anderes", "sonstiges", "other"}

    def join_lines(lines: list[str]) -> str | None:
        out = "\n".join([x for x in lines if x])
        return out or None

    rec = str(getattr(row, "recommended_plan", "") or "").strip().lower()
    rec_line = f"{label('Empfohlen', 'Рекомендовано')}: {rec}" if rec else ""

    if flow == "alcohol_v1":
        prom = g("promille_bucket")
        reason = g("mpu_reason")
        other = g("mpu_other")
        if is_other(reason) and other:
            reason = f"{label('Anderes', 'Другое')}: {other}"
        freq = g("drink_frequency")
        last = g("last_drink")
        lines = [
            f"{label('Thema', 'Тема')}: {label('Alkohol', 'алкоголь')}",
            f"{label('Promille', 'Промилле')}: {prom}" if prom else "",
            f"{label('Anlass', 'Причина направления')}: {reason}" if reason else "",
            f"{label('Häufigkeit', 'Частота')}: {freq}" if freq else "",
            f"{label('Letztes Mal', 'Последний раз')}: {last}" if last else "",
            rec_line,
        ]
        return join_lines(lines)

    if flow == "drugs_v1":
        sub = g("drug_substance")
        other = g("drug_other")
        if is_other(sub) and other:
            sub = f"{label('Anderes', 'Другое')}: {other}"
        basis = g("drug_basis")
        freq = g("drug_frequency")
        last = g("drug_last_use")
        lines = [
            f"{label('Thema', 'Тема')}: {label('Drogen', 'наркотики')}",
            f"{label('Substanz', 'Вещество')}: {sub}" if sub else "",
            f"{label('Basis', 'Основание')}: {basis}" if basis else "",
            f"{label('Häufigkeit', 'Частота')}: {freq}" if freq else "",
            f"{label('Letztes Mal', 'Последний раз')}: {last}" if last else "",
            rec_line,
        ]
        return join_lines(lines)

    if flow == "points_v1":
        bucket = g("points_bucket")
        reason = g("points_reason")
        other = g("points_other")
        if is_other(reason) and other:
            reason = f"{label('Anderes', 'Другое')}: {other}"
        freq = g("points_frequency")
        last = g("points_last")
        lines = [
            f"{label('Thema', 'Тема')}: {label('Punkte', 'штрафные баллы')}",
            f"{label('Punkte', 'Баллы')}: {bucket}" if bucket else "",
            f"{label('Grund', 'Причина')}: {reason}" if reason else "",
            f"{label('Häufigkeit', 'Частота')}: {freq}" if freq else "",
            f"{label('Letztes Mal', 'Последний раз')}: {last}" if last else "",
            rec_line,
        ]
        return join_lines(lines)

    if flow == "behavior_v1":
        itype = g("incident_type")
        other = g("incident_other")
        if is_other(itype) and other:
            itype = f"{label('Anderes', 'Другое')}: {other}"
        sev = g("incident_severity")
        patt = g("incident_pattern")
        last = g("incident_last")
        lines = [
            f"{label('Thema', 'Тема')}: {label('Vorfall', 'инцидент')}",
            f"{label('Typ', 'Тип')}: {itype}" if itype else "",
            f"{label('Schwere', 'Тяжесть')}: {sev}" if sev else "",
            f"{label('Muster', 'Повторяемость')}: {patt}" if patt else "",
            f"{label('Letztes Mal', 'Последний раз')}: {last}" if last else "",
            rec_line,
        ]
        return join_lines(lines)

    reasons = getattr(row, "reasons", None) or []
    if reasons:
        base = f"{label('Thema', 'Тема')}: {'/'.join([str(x) for x in reasons[:2]])}"
        return join_lines([base, rec_line])

    return rec_line or None


def _build_diagnostic_facts(repo: Repo, user_id: UUID, locale: str) -> dict[str, Any] | None:
    """Return structured diagnostic facts (source of truth for the coach).

    This is used to constrain LLM outputs: the assistant must not invent facts outside
    of these diagnostics + the user's own messages.
    """
    try:
        row = repo.get_latest_diagnostic_submission_for_user(user_id)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return None

    if not row:
        return None

    meta = getattr(row, "meta_json", None) or {}
    flow = str(meta.get("flow") or "").strip().lower() or None
    answers = meta.get("answers") or {}
    reasons = getattr(row, "reasons", None) or []
    plan = str(getattr(row, "recommended_plan", "") or "").strip().lower() or None

    # normalize for LLM
    def s(v: Any) -> str | None:
        if v is None:
            return None
        t = str(v).strip()
        return t or None

    facts: dict[str, Any] = {
        "locale": (locale or "de").strip().lower(),
        "flow": flow,
        "recommended_plan": plan,
        "reasons": [str(x) for x in reasons] if reasons else [],
        "answers": {k: v for k, v in (answers or {}).items() if s(v) is not None},
    }

    # convenience projections (common fields)
    a = facts["answers"]
    if isinstance(a, dict):
        if flow == "alcohol_v1":
            facts["promille_bucket"] = s(a.get("promille_bucket"))
            facts["mpu_reason"] = s(a.get("mpu_reason"))
            facts["mpu_other"] = s(a.get("mpu_other"))
            facts["drink_frequency"] = s(a.get("drink_frequency"))
            facts["last_drink"] = s(a.get("last_drink"))
        if flow == "drugs_v1":
            facts["drug_substance"] = s(a.get("drug_substance"))
            facts["drug_other"] = s(a.get("drug_other"))
            facts["drug_basis"] = s(a.get("drug_basis"))
            facts["drug_frequency"] = s(a.get("drug_frequency"))
            facts["drug_last_use"] = s(a.get("drug_last_use"))
        if flow == "points_v1":
            facts["points_bucket"] = s(a.get("points_bucket"))
            facts["points_reason"] = s(a.get("points_reason"))
            facts["points_other"] = s(a.get("points_other"))
            facts["points_frequency"] = s(a.get("points_frequency"))
            facts["points_last"] = s(a.get("points_last"))
        if flow == "behavior_v1":
            facts["incident_type"] = s(a.get("incident_type"))
            facts["incident_other"] = s(a.get("incident_other"))
            facts["incident_severity"] = s(a.get("incident_severity"))
            facts["incident_pattern"] = s(a.get("incident_pattern"))
            facts["incident_last"] = s(a.get("incident_last"))

    return facts


def _word_count(s: str) -> int:
    return len([x for x in re.split(r"\s+", (s or "").strip()) if x])


def _too_short_for_training(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return True
    if len(t) < 28:
        return True
    if _word_count(t) < 6:
        return True
    return False


@dataclass(frozen=True)
class OfficialQ:
    key: str
    question_de: str
    question_ru: str
    source: str
    essence_ru: str
    want_ru: list[str]
    avoid_ru: list[str]
    skeleton_ru: list[str]


OFFICIAL_ALCOHOL: dict[str, OfficialQ] = {
    "alc_authority_doubts": OfficialQ(
        key="alc_authority_doubts",
        question_de="Können Sie sich die Zweifel der Behörde an Ihrer Fahreignung erklären?",
        question_ru="Можешь объяснить, почему у ведомства возникли сомнения в твоей пригодности к вождению?",
        source="Gutachten (MPU Fragen, Seite 11)",
        essence_ru="Проверяют: понимаешь ли ты причину MPU и признаёшь ли риск для дорожной безопасности.",
        want_ru=[
            "Коротко назвать факт нарушения (без художеств).",
            "Прямо признать ответственность (без оправданий).",
            "Показать понимание риска (почему это опасно).",
            "Связать с изменениями: что сделал, чтобы исключить повтор.",
        ],
        avoid_ru=[
            "«Меня подставили/полиция придиралась/мне не повезло».",
            "Минимизация («ничего страшного», «я был нормальный»).",
            "Пустые обещания без механики контроля.",
        ],
        skeleton_ru=[
            "1) Факт: что было и что это значит для ведомства (сомнение в Fahreignung).",
            "2) Ответственность: «я принял решение / я ошибся / я отвечаю».",
            "3) Риск: чем это могло закончиться (ДТП, люди, последствия).",
            "4) Вывод + изменения: какие правила/меры теперь действуют и как ты их соблюдаешь.",
        ],
    ),
    "alc_past_use": OfficialQ(
        key="alc_past_use",
        question_de="Wie sind Sie früher mit Alkohol umgegangen?",
        question_ru="Как ты раньше употреблял алкоголь (как часто, сколько, в каких ситуациях)?",
        source="Gutachten (MPU Fragen, Seite 11)",
        essence_ru="Проверяют: был ли устойчивый паттерн, были ли триггеры, и умеешь ли ты говорить цифрами и ситуациями.",
        want_ru=[
            "Частота + количество в цифрах (пример: раз в 2 недели / 3–4 пива и т.п.).",
            "Контекст: где/с кем/почему (выходные, стресс, компания).",
            "Пик-сценарии: когда выходило из контроля (если было).",
            "Честно обозначить, что в этом было неправильного.",
        ],
        avoid_ru=[
            "Расплывчатое («иногда», «как все»).",
            "Несостыковки по времени/объёмам.",
            "Попытка выглядеть идеальным ценой выдумки.",
        ],
        skeleton_ru=[
            "1) База: как часто и сколько обычно.",
            "2) Ситуации: при каких обстоятельствах пил.",
            "3) Динамика: менялось ли со временем (почему).",
            "4) Признание проблемы: что было неправильного и к чему вело.",
        ],
    ),
    # добавь ключи (стр.12)
    "alc_amounts_avg_max": OfficialQ(
        key="alc_amounts_avg_max",
        question_de="Durchschnittliche und Höchsttrinkmengen mindestens im Einjahreszeitraum vor der Trunkenheitsfahrt:",
        question_ru="Какие были средние и максимальные количества алкоголя (минимум за год до Trunkenheitsfahrt)?",
        source="Gutachten, Seite 12",
        essence_ru="Проверяют: умеешь говорить цифрами и не путаешься в объёмах/частоте.",
        want_ru=[
            "Конкретные цифры (частота/объём).",
            "Отдельно: обычный максимум и день исключения.",
            "Увязать с весом/временем (если знаешь).",
            "Без противоречий с остальными фактами.",
        ],
        avoid_ru=["«Иногда/по-разному».", "Новые детали, которых не было в истории.", "Занижение/приукрашивание."],
        skeleton_ru=["1) Обычно: частота + объём.", "2) Максимум в обычные дни.", "3) Исключение (если было) — почему и сколько.", "4) Вывод: почему это было рискованно."],
    ),
    "alc_blackouts": OfficialQ(
        key="alc_blackouts",
        question_de="Ob nach hohem Alkoholkonsum jemals Erinnerungslücken oder Filmrisse aufgetreten seien:",
        question_ru="Были ли когда-либо провалы памяти/«фильмриcсы» после алкоголя?",
        source="Gutachten, Seite 12",
        essence_ru="Проверяют: уровень потери контроля и честность.",
        want_ru=["Прямой ответ да/нет.", "Если да — когда/как часто/какие последствия.", "Связать с выводом: это маркер опасного употребления."],
        avoid_ru=["Уход от ответа.", "Смена темы на «но я хороший»."],
        skeleton_ru=["1) Да/нет.", "2) Короткий факт (когда/как проявлялось).", "3) Последствия.", "4) Почему это показатель риска и что изменено теперь."],
    ),
    "alc_criticism_environment": OfficialQ(
        key="alc_criticism_environment",
        question_de="Ob es kritische Hinweise gegeben habe:",
        question_ru="Были ли критические замечания/сигналы от окружения по твоему употреблению?",
        source="Gutachten, Seite 12",
        essence_ru="Проверяют: обратная связь, конфликты, отрицание.",
        want_ru=["Кто говорил и что именно.", "Как ты реагировал тогда.", "Что понял сейчас."],
        avoid_ru=["«Никто не говорил» при явных признаках проблемы (если они были)."],
        skeleton_ru=["1) Были/не были.", "2) Кто и в каком контексте.", "3) Моя реакция тогда.", "4) Мой вывод сейчас."],
    ),
    "alc_neglect_duties": OfficialQ(
        key="alc_neglect_duties",
        question_de="Ob er in der Vergangenheit als Folge seines Alkoholtrinkens seine normalen privaten und beruflichen Pflichten vernachlässigt habe:",
        question_ru="Были ли случаи, когда из-за алкоголя ты забивал на работу/быт/обязательства?",
        source="Gutachten, Seite 12",
        essence_ru="Проверяют: степень ущерба и самооценку риска.",
        want_ru=["Прямо да/нет.", "Если да — примеры.", "Связать с изменениями."],
        avoid_ru=["Общее «нет» при наличии других негативных эффектов (если они были описаны)."],
        skeleton_ru=["1) Да/нет.", "2) 1–2 примера (если да).", "3) Последствия.", "4) Что теперь по-другому."],
    ),
    "alc_negative_effects": OfficialQ(
        key="alc_negative_effects",
        question_de="Auf Nachfrage nach negativen Auswirkungen des Alkoholkonsums bzw. welche Nachteile er durch den Konsum erfahren habe:",
        question_ru="Какие негативные последствия давал алкоголь (физически/психически/социально)?",
        source="Gutachten, Seite 12",
        essence_ru="Проверяют: осознание вреда, а не «всё норм».",
        want_ru=["2–4 конкретных эффекта.", "Короткие примеры.", "Связь с риском вождения."],
        avoid_ru=["«Никаких» без объяснения."],
        skeleton_ru=["1) Негатив №1 + пример.", "2) Негатив №2 + пример.", "3) Как это влияет на решения/контроль.", "4) Почему это несовместимо с безопасным вождением."],
    ),
    "alc_problem_insight": OfficialQ(
        key="alc_problem_insight",
        question_de="Ob er ein Problem in seinem damaligen Konsum sehe bzw. warum:",
        question_ru="Видишь ли ты проблему в своём тогдашнем употреблении и почему?",
        source="Gutachten, Seite 12",
        essence_ru="Проверяют: инсайт (признание) и логика причинно-следственной связи.",
        want_ru=["Чётко: да, видел/не видел тогда, но вижу сейчас.", "Почему это было проблемой.", "Что изменилось в голове/поведении."],
        avoid_ru=["Оправдания вместо причины."],
        skeleton_ru=["1) Тогда: как я это воспринимал.", "2) Сейчас: в чём проблема.", "3) Почему я это недооценивал.", "4) Что теперь иначе (правила/контроль)."],
    ),
    # добавь ключи (стр.13)
    "alc_why_not_avoided": OfficialQ(
        key="alc_why_not_avoided",
        question_de="Wieso er diese Trunkenheitsfahrt nicht vermieden habe:",
        question_ru="Почему ты не избежал Trunkenheitsfahrt? Что стало решающим триггером?",
        source="Gutachten, Seite 13",
        essence_ru="Проверяют: реальная причина (триггер) и план альтернатив.",
        want_ru=["Одна главная причина (без рассыпания).", "Какие альтернативы были и почему их не выбрал.", "Как теперь ты это предотвращаешь."],
        avoid_ru=["«Не знаю» как единственный ответ.", "«Само получилось»."],
        skeleton_ru=["1) Триггер/решающий момент.", "2) Почему контроль упал.", "3) Какие альтернативы были.", "4) Что теперь стоит барьером."],
    ),
    "alc_felt_fit": OfficialQ(
        key="alc_felt_fit",
        question_de="Auf Nachfrage, ob er sich fahrtüchtig gefühlt habe und nach alkoholbedingten Einschränkungen:",
        question_ru="Чувствовал ли ты себя «в порядке» для езды и какие были ограничения/симптомы?",
        source="Gutachten, Seite 13",
        essence_ru="Проверяют: самообман и маркеры опьянения.",
        want_ru=["Признать, что оценка была ошибочной.", "Назвать симптомы/состояние (если было).", "Вывод: доверять ощущениям нельзя, нужны правила."],
        avoid_ru=["«Я был нормальный»."],
        skeleton_ru=["1) Что я чувствовал тогда.", "2) Почему это было неверно.", "3) Какие признаки были/могли быть.", "4) Как теперь исключаю решение “по ощущениям”."],
    ),
    "alc_drink_drive_organization": OfficialQ(
        key="alc_drink_drive_organization",
        question_de="Auf Nachfrage, wie er früher Fahren und Trinken organisiert habe:",
        question_ru="Как раньше ты организовывал «пить/ездить» (транспорт, план, ночёвка)?",
        source="Gutachten, Seite 13",
        essence_ru="Проверяют: были ли системные меры или хаос.",
        want_ru=["Как планировал раньше (если планировал).", "Где был провал.", "Какая система сейчас."],
        avoid_ru=["Фантазии без конкретики."],
        skeleton_ru=["1) Как было раньше.", "2) Где ломалось.", "3) Что теперь по правилам.", "4) Пример сценария (что делаю, если выпил)."],
    ),
    "alc_change_when": OfficialQ(
        key="alc_change_when",
        question_de="Ob bzw. dann wann er sein Trinkverhalten geändert habe:",
        question_ru="Когда и как ты изменил своё употребление (точка/период/что именно)?",
        source="Gutachten, Seite 13",
        essence_ru="Проверяют: реальный переход и стабильность изменений.",
        want_ru=["Когда начал менять.", "Что конкретно изменил.", "Как закрепил (правила/учёт/поддержка)."],
        avoid_ru=["«С тех пор по-другому» без механики."],
        skeleton_ru=["1) Когда/почему старт изменений.", "2) Что изменил (частота/объём/контекст).", "3) Как контролирую.", "4) Что делаю при риске срыва."],
    ),
    # добавь ключи (стр.14)
    "alc_group_pressure": OfficialQ(
        key="alc_group_pressure",
        question_de="Wie er mit sozialen Verführungssituationen und Gruppendruck umgehe:",
        question_ru="Как ты справляешься с соблазнами/групповым давлением (вечеринки, друзья)?",
        source="Gutachten, Seite 14",
        essence_ru="Проверяют: стратегии в реальных социальных ситуациях.",
        want_ru=["2–3 конкретные стратегии.", "Фразы/скрипты отказа.", "План выхода из ситуации."],
        avoid_ru=["«Просто не пью» без стратегии."],
        skeleton_ru=["1) Типовая ситуация.", "2) Как распознаю риск.", "3) Что делаю (конкретно).", "4) План выхода/поддержка."],
    ),
    "alc_rules": OfficialQ(
        key="alc_rules",
        question_de="Ob er sich Trinkregeln gesetzt habe:",
        question_ru="Установил ли ты для себя Trinkregeln (правила употребления)? Какие?",
        source="Gutachten, Seite 14",
        essence_ru="Проверяют: наличие измеримых правил и контроль исполнения.",
        want_ru=["Правила в цифрах/условиях.", "Как отслеживаешь.", "Что делаешь при нарушении."],
        avoid_ru=["Размытые правила."],
        skeleton_ru=["1) Мои правила (пункты).", "2) Как фиксирую/контролирую.", "3) Барьеры (транспорт/время).", "4) Что делаю, если риск растёт."],
    ),
    # добавь ключи (стр.15)
    "alc_avoid_future_dui": OfficialQ(
        key="alc_avoid_future_dui",
        question_de="Wie er zukünftig zuverlässig erneute Trunkenheitsfahrten vermeiden wolle:",
        question_ru="Как ты гарантированно будешь избегать повторной езды после алкоголя?",
        source="Gutachten, Seite 15",
        essence_ru="Проверяют: барьеры и альтернативы, не обещания.",
        want_ru=["Правило «алкоголь = 0 вождения» в форме системы.", "Альтернативы: ÖPNV/Taxi/друг/ночёвка.", "План на неожиданности."],
        avoid_ru=["«Буду аккуратнее»."],
        skeleton_ru=["1) Мой принцип.", "2) Как планирую транспорт заранее.", "3) Что делаю в неожиданных ситуациях.", "4) Как проверяю, что соблюдаю правило."],
    ),
    "alc_relapse_risk": OfficialQ(
        key="alc_relapse_risk",
        question_de="Wie er seine persönliche Rückfallgefährdung einschätze:",
        question_ru="Как ты оцениваешь свой риск рецидива (возврата к старому паттерну) и почему?",
        source="Gutachten, Seite 15",
        essence_ru="Проверяют: честная оценка риска + план управления.",
        want_ru=["Где риск выше всего.", "Триггеры.", "План действий/поддержка."],
        avoid_ru=["«Риска нет вообще»."],
        skeleton_ru=["1) Мой риск (где/когда).", "2) Триггеры.", "3) Ранние признаки.", "4) План действий."],
    ),
}

COURSE_FLAG_POLICY: dict[str, set[str]] = {
    # Q1: сомнения ведомства — важны ответственность + меры, таймлайн не критичен
    "alc_authority_doubts": {"blame_shift", "missing_actions"},
    # Q2: как раньше пил — важна конкретика/паттерн, таймлайн/факты
    "alc_past_use": {"missing_timeline"},
}


def _course_needs_rewrite(flags: dict[str, Any], cur_key: str, user_text: str) -> bool:
    # Базовый гейт: в курсе нельзя принимать короткие ответы (иначе курс превращается в чат).
    words = len([x for x in re.split(r"\s+", (user_text or "").strip()) if x])
    if words < 25:
        return True

    t = (user_text or "").strip()
    low = t.lower()

    # Ключевые вопросы имеют обязательные элементы. Это НЕ LLM-логика — это жёсткий валидатор.
    # 1) Критические замечания: должен быть 1 человек + 1 фраза/пересказ, иначе начинаются додумки.
    if cur_key == "alc_criticism_environment":
        has_phrase = ("«" in t) or ('"' in t) or bool(re.search(r"\b(сказал|сказала|говорил|говорила|говорили)\b", low))
        if not has_phrase:
            return True

    # 2) Средние/максимальные количества: нужны цифры (иначе ответ бесполезен на интервью).
    if cur_key == "alc_amounts_avg_max":
        if not re.search(r"\d", t):
            return True

    # 3) Провалы памяти: обязан быть прямой "да/нет" (или эквивалент) в начале.
    if cur_key == "alc_blackouts":
        head = " ".join((low.split() or [])[:8])
        if not any(x in head for x in ("да", "нет", "были", "не было", "не было никогда")):
            return True

    # 4) Негативные эффекты: минимум 2 конкретных последствия.
    if cur_key == "alc_negative_effects":
        parts = [x.strip() for x in re.split(r"[\n\.]+", t) if x.strip()]
        if len(parts) < 2:
            return True

    # 5) Правила: должно быть хотя бы одно измеримое правило или принцип "0 вождения после алкоголя".
    if cur_key in {"alc_rules", "alc_avoid_future_dui"}:
        if not (re.search(r"\d", t) or ("нулев" in low) or ("0" in t) or ("не саж" in low and "рул" in low)):
            return True

    policy = COURSE_FLAG_POLICY.get(cur_key)
    if not policy:
        # дефолт: для большинства вопросов таймлайн не обязателен;
        # блокируем только при отсутствии конкретных действий или уходе от ответственности.
        return bool(flags.get("missing_actions") or flags.get("blame_shift"))

    return any(bool(flags.get(k)) for k in policy)


def _extract_course_state(history: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not history:
        return None
    for msg in reversed(history):
        if str(msg.get("role") or "").strip().lower() != "assistant":
            continue
        text = str(msg.get("content") or "")
        for line in text.splitlines():
            t = line.strip()
            if t.startswith("[[COURSE]]"):
                raw = t[len("[[COURSE]]") :].strip()
                try:
                    obj = json.loads(raw)
                    return obj if isinstance(obj, dict) else None
                except Exception:
                    return None
    return None


def _course_yes(text: str, locale: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    # tolerate punctuation/emojis from quick-action buttons and casual replies
    t = re.sub(r"[^\w\sа-яё]", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return False
    if (locale or "de").startswith("ru"):
        return t in {"да", "давай", "готов", "поехали", "начинаем", "ок", "окей", "ага", "угу"} or t.startswith("да ")
    return t in {"ja", "los", "start", "ok"} or t.startswith("ja ")


def _course_start_intent(text: str, locale: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if (locale or "de").startswith("ru"):
        return t in {
            "начать",
            "начать обучение",
            "старт",
            "поехали",
            "давай начнем",
            "давай начнём",
            "/start",
            "start",
        }
    return t in {"start", "/start", "los", "beginnen"}


def _should_reuse_last_assistant_for_same_user_text(
    *,
    incoming_text: str,
    last_user_text: str,
    last_user_created_at: datetime,
    last_assistant_created_at: datetime | None,
    now_utc: datetime,
) -> bool:
    if (incoming_text or "").strip() != (last_user_text or "").strip():
        return False

    # Классический retry сразу после 50x/timeout.
    age_s = (now_utc - last_user_created_at).total_seconds()
    if 0 <= age_s < 4:
        return True

    # Доп. защита: если ассистент уже ответил на этот же последний user-mesage,
    # а фронт повторно отправил тот же текст (двоеклик/ретрай), не плодим дубли.
    if last_assistant_created_at is None:
        return False
    if last_assistant_created_at < last_user_created_at:
        return False

    # Окно ограничиваем, чтобы не блокировать осознанный повтор спустя долгое время.
    return 0 <= age_s < 180



def _parse_day_of_30(boot_params: dict[str, str]) -> tuple[int, int]:
    day_raw = (boot_params.get("day") or "").strip()
    if not day_raw:
        return 1, 30
    # "7/30" или "7"
    try:
        if "/" in day_raw:
            a, b = day_raw.split("/", 1)
            d = int(a.strip())
            of = int(b.strip())
            return max(1, d), max(1, of)
        return max(1, int(day_raw)), 30
    except Exception:
        return 1, 30

_BERLIN_TZ = ZoneInfo("Europe/Berlin")

def _berlin_today() -> date:
    return datetime.now(_BERLIN_TZ).date()


def _course_clock_sync(course: dict[str, Any]) -> tuple[int, str, int]:
    """
    Возвращает:
      day_now: текущий день курса 1..of по календарю Europe/Berlin
      start_date_str: YYYY-MM-DD (Europe/Berlin)
      of: длительность курса (обычно 30)
    """
    try:
        of = int(course.get("of") or 30)
    except Exception:
        of = 30

    today = _berlin_today()

    start_s = str(course.get("start_date") or "").strip()
    if start_s:
        try:
            start_d = date.fromisoformat(start_s)
        except Exception:
            start_d = today
            start_s = start_d.isoformat()
    else:
        # если start_date отсутствует (старые сессии) — восстанавливаем так,
        # чтобы текущий course["day"] остался тем же, но привязался к календарю.
        try:
            cur_day = int(course.get("day") or 1)
        except Exception:
            cur_day = 1
        start_d = date.fromordinal(today.toordinal() - max(0, cur_day - 1))
        start_s = start_d.isoformat()

    day_now = (today - start_d).days + 1
    if day_now < 1:
        day_now = 1
    if day_now > of:
        day_now = of

    return day_now, start_s, of


def _prepare_alcohol_day_state(db: Session, *, day_int: int, of: int, loc: str, start_date: str) -> tuple[dict[str, Any], list[OfficialQ], dict[str, Any]]:
    module, keys, drill_tags = _pick_alcohol_day_keys(day_int)

    drill = None
    try:
        drill = next_question(db, locale=loc, mode="practice", topic_id=None, required_tags=drill_tags)
    except Exception:
        drill = None
    if drill and _looks_non_ru_question(drill):
        translated = translate_question_to_ru(drill)
        drill = translated.strip() if translated and translated.strip() else None

    qs = [OFFICIAL_ALCOHOL[k] for k in keys if k in OFFICIAL_ALCOHOL]

    state: dict[str, Any] = {
        "v": 2,
        "phase": "intro",
        "i": 0,
        "keys": keys,
        "day": day_int,
        "of": of,
        "module": module,
        "drill": drill,
        "start_date": start_date,  # ВАЖНО: привязка к календарю
    }

    plan = _build_day_plan_ru(day_int, of, module, keys, drill)
    return state, qs, plan

ALC_POOL_ORDER = [
    "alc_authority_doubts",
    "alc_past_use",
    "alc_amounts_avg_max",
    "alc_blackouts",
    "alc_negative_effects",
    "alc_problem_insight",
    "alc_criticism_environment",
    "alc_neglect_duties",
    "alc_why_not_avoided",
    "alc_felt_fit",
    "alc_drink_drive_organization",
    "alc_change_when",
    "alc_rules",
    "alc_group_pressure",
    "alc_avoid_future_dui",
    "alc_relapse_risk",
]


def _pick_alcohol_day_keys(day: int) -> tuple[str, list[str], list[str]]:
    """
    Возвращает: module_title, [k1,k2], drill_tags
    1–8: проход по пулу
    9–20: закрепление (перемешанные пары)
    21–30: mock (давление/скорость) — тоже реальные вопросы, но другие ограничения
    """
    d = max(1, day)
    pool = ALC_POOL_ORDER

    if d <= 8:
        base = (d - 1) * 2
        keys = [pool[base % len(pool)], pool[(base + 1) % len(pool)]]
        return "Фундамент", keys, ["facts", "timeline"]

    if d <= 20:
        base = ((d - 9) * 3) % len(pool)
        keys = [pool[base], pool[(base + 5) % len(pool)]]
        return "Закрепление", keys, ["responsibility", "plan", "prevention"]

    base = (d * 5) % len(pool)
    keys = [pool[base], pool[(base + 1) % len(pool)]]
    return "Mock под давлением", keys, ["pressure", "coherence", "strategy"]


def _build_day_plan_ru(day: int, of: int, module: str, keys: list[str], drill_text: str | None) -> dict[str, Any]:
    qs = []
    for k in keys:
        q = OFFICIAL_ALCOHOL.get(k)
        if not q:
            continue
        qs.append({"type": "official", "key": k, "question": q.question_ru, "source": q.source})

    drills = []
    if drill_text:
        drills.append({"type": "drill", "question": drill_text})

    return {
        "day": day,
        "of": of,
        "title": f"День {day}/{of}: {module}",
        "module": module,
        "agenda": [
            "Разбор вопроса №1 (суть/что хотят/что избегать) + черновик + переписывание",
            "Разбор вопроса №2 (суть/что хотят/что избегать) + черновик + переписывание",
            "Короткий дрилл на слабое место (если нужно)",
        ],
        "questions": qs,
        "drills": drills,
        "success_criteria": [
            "Ответ 5–8 предложений, без воды",
            "Есть факты/таймлайн",
            "Есть ответственность без оправданий",
            "Есть конкретные изменения/барьеры",
        ],
        "timebox_min": 25,
    }


def _render_diag_hint_ru(diagnostic_summary: str | None) -> str:
    s = (diagnostic_summary or "").strip()
    if not s:
        return ""
    lines = [x.strip() for x in s.splitlines() if x.strip()]
    lines = lines[:4]
    if not lines:
        return ""
    return "Твой контекст (из диагностики):\n" + "\n".join([f"- {x}" for x in lines])


def _render_course_intro_ru(qs: list[OfficialQ], *, diagnostic_summary: str | None = None) -> str:
    diag = _render_diag_hint_ru(diagnostic_summary)
    lines = [
        "Привет. Это тренировка MPU: я веду тебя как тренер, а не просто задаю вопросы.",
        "",
    ]
    if diag:
        lines += [diag, ""]
    lines += [
        "Как мы работаем:",
        "1) Я объясняю, что проверяют в вопросе (суть/что хотят/что избегать).",
        "2) Ты даёшь черновик (5–8 предложений). Если чего-то не знаешь — так и пиши.",
        "3) Я разбираю и даю сильный шаблон.",
        "4) Ты переписываешь до прохода. Только после этого идём дальше.",
        "",
        "Сегодня разберём 2 реальных вопроса (по источнику):",
    ]
    for i, q in enumerate(qs, 1):
        lines.append(f"{i}) {q.question_ru} — источник: {q.source}")
    lines += [
        "",
        "Начинаем вопросы? Ответь: «да».",
    ]
    return "\n".join(lines).strip()


def _render_lesson_ru(q: OfficialQ, idx: int, total: int, *, diagnostic_summary: str | None = None, show_context: bool = False) -> str:
    diag = _render_diag_hint_ru(diagnostic_summary) if show_context else ""
    lines = [
        f"Вопрос {idx}/{total} — источник: {q.source}",
        f"Вопрос: {q.question_ru}",
        "",
    ]
    if diag:
        lines += [diag, ""]
    lines += [
        f"Суть: {q.essence_ru}",
        "",
        "Что хотят услышать:",
        *[f"- {x}" for x in q.want_ru],
        "",
        "Чего избегать:",
        *[f"- {x}" for x in q.avoid_ru],
        "",
        "Скелет сильного ответа (5–8 предложений):",
        *[f"- {x}" for x in q.skeleton_ru],
        "",
        "Ок. Теперь твой черновик (5–8 предложений):",
    ]
    return "\n".join(lines).strip()


def _too_short_pressure_answer_ru(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return True
    # В pressure-дрилле короче, чем в обычной тренировке: 2–4 предложения.
    if _word_count(t) < 12:
        return True
    # Если это одна короткая строка — почти всегда не годится.
    if ("." not in t and "\n" not in t) and len(t) < 80:
        return True
    return False

def _too_short_homework_answer_ru(s: str) -> bool:
    """Home drill: allow shorter than full training, but still needs substance."""
    t = (s or "").strip()
    if not t:
        return True
    # 4–6 sentences ≈ 18+ words in practice.
    if _word_count(t) < 18:
        return True
    if len(t) < 90:
        return True
    return False

PRESSURE_DRILLS_RU: dict[str, list[str]] = {
    "alc_authority_doubts": [
        "Вы говорите, что понимаете сомнения ведомства. В чём конкретно был риск для других участников движения — одним предложением.",
        "Почему это было вашей ответственностью, а не «обстоятельствами»? Скажи прямо, без оправданий.",
    ],
    "alc_past_use": [
        "Назови одну типовую ситуацию из прошлого: где, с кем, и сколько примерно выпивал. Без общих слов.",
        "Что было самым частым триггером на выпивку и как ты это распознаёшь сейчас?",
    ],
    "alc_amounts_avg_max": [
        "Назови: обычный максимум и самый высокий максимум за год до случая. Если не помнишь — скажи, как ты бы это оценил честно.",
    ],
    "alc_blackouts": [
        "Если у тебя были «провалы», почему это опасный маркер для контроля? Ответь без теории — по себе.",
    ],
    "alc_negative_effects": [
        "Назови один негативный эффект, который реально тебя задел, и как он влиял на решения/самоконтроль.",
    ],
    "alc_problem_insight": [
        "В чём была проблема именно у тебя — один конкретный критерий, по которому ты сейчас это оцениваешь.",
    ],
    "alc_criticism_environment": [
        "Кто конкретно говорил тебе об этом? Назови одного человека и одну фразу, которую он сказал.",
        "Почему ты тогда не воспринял это всерьёз? Что ты себе говорил в голове?",
        "Что именно в этих замечаниях ты считаешь правдой сейчас?",
    ],
    "alc_neglect_duties": [
        "Дай один пример, где алкоголь помешал обязательствам. Если не было — объясни, почему риск всё равно существовал.",
    ],
    "alc_why_not_avoided": [
        "Почему в тот момент ты не выбрал альтернативу (такси/ÖPNV/ночёвка)? Что было решающим фактором?",
    ],
    "alc_felt_fit": [
        "Почему «я чувствовал себя нормально» — плохой критерий? Скажи, какой критерий используешь теперь.",
    ],
    "alc_drink_drive_organization": [
        "Опиши, как ты организуешь транспорт теперь, если есть вероятность алкоголя. Один сценарий от начала до конца.",
    ],
    "alc_change_when": [
        "Что изменилось первым: мышление или конкретные правила? Назови один момент/период и одну меру.",
    ],
    "alc_rules": [
        "Назови одно правило в цифрах/условиях и как ты проверяешь его соблюдение.",
    ],
    "alc_group_pressure": [
        "Как ты отказываешься в компании: одна фраза отказа + что делаешь дальше (уход/альтернатива).",
    ],
    "alc_avoid_future_dui": [
        "Если план сорвался (неожиданная ситуация) — что ты делаешь, чтобы не принять решение «по ощущениям»?",
    ],
    "alc_relapse_risk": [
        "Где твой риск выше всего и что ты делаешь в первые 10 минут, когда замечаешь риск?",
    ],
}


def _pick_pressure_drill_ru(key: str, *, seed: int = 0) -> str:
    pool = PRESSURE_DRILLS_RU.get(str(key or "").strip()) or []
    if not pool:
        return "Ответь как на интервью: 2–4 предложения, факты → ответственность → барьер/альтернатива."
    idx = abs(int(seed)) % len(pool)
    return pool[idx]


def _boot_message(locale: str, mode: str) -> str:
    loc = (locale or "de").strip().lower()
    if loc.startswith("ru"):
        if mode == "mock":
            return "Старт экзамена. Отвечай как на интервью: факты → ответственность → изменения → контроль риска."
        return "Ок, начнём тренировку. Отвечай 5–8 предложений: факты → ответственность → изменения → контроль риска."
    if mode == "mock":
        return "Prüfung gestartet. Antworten Sie wie im Interview: Fakten → Verantwortung → Veränderungen → Risikokontrolle."
    return "Training gestartet. Antworten Sie in 5–8 Sätzen: Fakten → Verantwortung → Veränderungen → Risikokontrolle."


def _start_question(locale: str) -> str:
    loc = (locale or "de").strip().lower()
    if loc.startswith("ru"):
        return "Коротко опиши вашу ситуацию: что произошло, когда/где, и в чём твоя ответственность?"
    return "Beschreiben Sie Ihren Fall kurz: was ist passiert, wann/wo, und welche Verantwortung übernehmen Sie?"

def _match_official_key_ru(question_text: str | None) -> str | None:
    """Best-effort mapping: RU question text -> OFFICIAL_ALCOHOL key."""
    q = (question_text or "").strip()
    if not q:
        return None
    qn = re.sub(r"\s+", " ", q).strip().lower()
    for k, obj in OFFICIAL_ALCOHOL.items():
        cand = re.sub(r"\s+", " ", (obj.question_ru or "").strip()).lower()
        if not cand:
            continue
        if qn == cand or qn.startswith(cand) or cand.startswith(qn):
            return k
    return None

def _clarify_message(locale: str, mode: str, *, key: str | None = None, question: str | None = None) -> str:
    loc = (locale or "de").strip().lower()

    if loc.startswith("ru"):
        header = "Ответ слишком короткий: сейчас это не годится для интервью MPU."
        if mode == "mock":
            header = "Ответ непригоден для интервью MPU: слишком коротко и без проверяемых фактов."

        k = (key or "").strip()

        # Вопрос: замечания окружения (НЕ тащи сюда BAK/маршрут/полицию)
        if k == "alc_criticism_environment":
            need = (
                "Нужно 5–8 предложений и конкретика (без выдумок):\n"
                "- кто конкретно говорил (1–2 человека)\n"
                "- когда примерно (период/год)\n"
                "- при каких обстоятельствах (дома/после встречи/переписка и т.п.)\n"
                "- что именно сказали (суть одной фразы)\n"
                "- как ты реагировал тогда\n"
                "- что понял сейчас\n"
                "- что изменил и как контролируешь, чтобы не повторить\n"
            )
            template = (
                "Шаблон (заполни [ ], не придумывай):\n"
                "«В [период] в [город/место] [кто] сказал(а) мне: [суть замечания]. "
                "Ещё [кто] в [обстоятельства] отметил(а): [суть]. "
                "Тогда я реагировал [как: спорил/отмахивался/минимизировал] и думал [что себе говорил]. "
                "Сейчас я понимаю, что это было [отрицание/самообман] и почему это опасно. "
                "После инцидента я изменил(а): [2–3 конкретных правила]. "
                "Контроль: [какой барьер стоит / как заранее планирую транспорт / что делаю при риске].»"
            )
            next_step = "Следующий шаг: перепиши ответ по этому шаблону (5–8 предложений)."
            return f"{header}\n\n{need}\n{template}\n\n{next_step}"

        # Вопрос: забивал на работу/быт/обязательства (тут нужны примеры и последствия)
        if k == "alc_neglect_duties":
            need = (
                "Нужно 5–8 предложений и конкретика (без выдумок):\n"
                "- прямой ответ: да/нет\n"
                "- если да: 1–2 конкретных примера (работа/быт/обязательства)\n"
                "- последствия (что сорвалось/какой ущерб)\n"
                "- что понял сейчас (почему это маркер риска)\n"
                "- что изменил и как контролируешь, чтобы не повторить\n"
            )
            template = (
                "Шаблон (заполни [ ], не придумывай):\n"
                "«[Да/Нет]. Если да: в [период] из-за алкоголя я [что именно не сделал/сорвал] в [контекст]. "
                "Это привело к [последствие]. Тогда я [как объяснял себе/как реагировал]. "
                "Сейчас я понимаю, что это показывало [потерю контроля/неправильные приоритеты] и повышало риск повторения. "
                "Теперь я делаю иначе: [2–3 конкретных правила/барьера] и [как проверяю соблюдение].»"
            )
            next_step = "Следующий шаг: перепиши ответ по этому шаблону (5–8 предложений)."
            return f"{header}\n\n{need}\n{template}\n\n{next_step}"

        # Фолбэк (оставляем твой текущий универсальный шаблон для “инцидентных” вопросов)
        need = (
            "Нужно 5–8 предложений и конкретика (без выдумок):\n"
            "- когда (дата/период)\n"
            "- где (город/место)\n"
            "- сколько/что пил и за какой промежуток\n"
            "- почему всё равно сел за руль (решение/триггер)\n"
            "- чем закончилось (полиция/BAK/наказание)\n"
            "- что изменил после (правила, контроль риска, альтернативы)\n"
        )
        template = (
            "Шаблон (заполни плейсхолдеры, не придумывай):\n"
            "«[дата/период] в [город/место] я был [где/с кем] и выпил [что/сколько] за [время]. "
            "Несмотря на это, я принял решение сесть за руль и проехал [дистанция/маршрут]. "
            "Это закончилось так: [остановка/ДТП/проверка]. Официальный показатель: [BAK/промилле]. "
            "Моя ответственность: [2 предложения без оправданий]. "
            "После этого я изменил поведение: [3 конкретных правила]. "
            "Контроль риска: [как предотвращаю повторение и как проверяю себя].»"
        )
        next_step = "Следующий шаг: перепиши ответ по этому шаблону (5–8 предложений)."
        q_line = f"Текущий вопрос: {question}\n\n" if question else ""
        return f"{header}\n\n{q_line}{need}\n{template}\n\n{next_step}"

    # DE-часть оставь как есть (можно просто скопировать из текущей функции без изменений)
    header = "Antwort ist zu kurz. So ist das im MPU-Interview nicht verwertbar."
    if mode == "mock":
        header = "Antwort ist für MPU-Interview unbrauchbar: zu kurz und ohne überprüfbare Fakten."
    need = (
        "Gib 5–8 Sätze und konkrete Fakten (ohne Erfinden):\n"
        "- wann (Datum/Zeitraum)\n"
        "- wo (Ort/Stadt)\n"
        "- was/wie viel und über welchen Zeitraum\n"
        "- warum trotzdem gefahren (Trigger/Entscheidung)\n"
        "- wie endete es (Polizei/BAK/Sanktion)\n"
        "- was hat sich geändert (Regeln, Risikokontrolle, Alternativen)\n"
    )
    template = (
        "Vorlage (Platzhalter ausfüllen, nichts erfinden):\n"
        "„[Datum/Zeitraum] in [Ort] war ich [mit wem/wo] und habe [was/wie viel] über [Dauer] getrunken. "
        "Trotzdem habe ich entschieden zu fahren und bin [Strecke/Route] gefahren. "
        "Es endete so: [Kontrolle/Unfall/Test]. Offizieller Wert: [BAK/Promille]. "
        "Meine Verantwortung: [2 Sätze ohne Ausreden]. "
        "Danach habe ich mein Verhalten geändert: [3 konkrete Regeln]. "
        "Risikokontrolle: [wie Rückfälle verhindert werden].“"
    )
    next_step = "Nächster Schritt: Schreibe die Antwort nach dieser Vorlage (5–8 Sätze)."
    return f"{header}\n\n{need}\n{template}\n\n{next_step}"

    header = "Antwort ist zu kurz. So ist das im MPU-Interview nicht verwertbar."
    if mode == "mock":
        header = "Antwort ist für MPU-Interview unbrauchbar: zu kurz und ohne überprüfbare Fakten."
    need = (
        "Gib 5–8 Sätze und konkrete Fakten (ohne Erfinden):\n"
        "- wann (Datum/Zeitraum)\n"
        "- wo (Ort/Stadt)\n"
        "- was/wie viel und über welchen Zeitraum\n"
        "- warum trotzdem gefahren (Trigger/Entscheidung)\n"
        "- wie endete es (Polizei/BAK/Sanktion)\n"
        "- was hat sich geändert (Regeln, Risikokontrolle, Alternativen)\n"
    )
    template = (
        "Vorlage (Platzhalter ausfüllen, nichts erfinden):\n"
        "„[Datum/Zeitraum] in [Ort] war ich [mit wem/wo] und habe [was/wie viel] über [Dauer] getrunken. "
        "Trotzdem habe ich entschieden zu fahren und bin [Strecke/Route] gefahren. "
        "Es endete so: [Kontrolle/Unfall/Test]. Offizieller Wert: [BAK/Promille]. "
        "Meine Verantwortung: [2 Sätze ohne Ausreden]. "
        "Danach habe ich mein Verhalten geändert: [3 konkrete Regeln]. "
        "Risikokontrolle: [wie Rückfälle verhindert werden].“"
    )
    next_step = "Nächster Schritt: Schreibe die Antwort nach dieser Vorlage (5–8 Sätze)."
    return f"{header}\n\n{need}\n{template}\n\n{next_step}"


# --- Anti-hallucination sanitation (server-side safety net) ---

_TIME_OF_DAY_RE = re.compile(r"\b(?:[01]?\d|2[0-3])[:.][0-5]\d\b")
_RU_HOUR_RE = re.compile(r"\b(?:в|около|примерно|приблизительно)\s*(?:[01]?\d|2[0-3])\s*час(?:а|ов)?\b", re.IGNORECASE)

# Поддерживаем диапазоны вроде "0.8–1.5‰"
_PROMILLE_RANGE_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)(?:\s*[–-]\s*(\d+(?:[.,]\d+)?))?\s*(?:промилле|‰)\b", re.IGNORECASE)
_PROMILLE_WORD_RE = re.compile(r"\bпромилле\b", re.IGNORECASE)

_RU_MONTH_RE = re.compile(
    r"\b(?:январ[ьяе]|феврал[ьяе]|март[ае]?|апрел[ьяе]|ма[йя]|июн[ьяе]|июл[ьяe]|август[ае]?|сентябр[ьяе]|октябр[ьяе]|ноябр[ьяe]|декабр[ьяe])\b",
    re.IGNORECASE,
)
_RU_MONTH_PHRASE_RE = re.compile(
    r"\b(?:в\s+(?:начале|середине|конце)\s+)?"
    r"(?:январ[ьяе]|феврал[ьяе]|март[ае]?|апрел[ьяе]|ма[йя]|июн[ьяе]|июл[ьяe]|август[ае]?|сентябр[ьяe]|октябр[ьяe]|ноябр[ьяe]|декабр[ьяe])\b",
    re.IGNORECASE,
)

_RELATIVE_TIME_RU_RE = re.compile(r"\b(?:вчера|позавчера|сегодня|на прошлой неделе|на прошлых выходных)\b", re.IGNORECASE)

_NEXT_LINE_RU_RE = re.compile(r"(?im)^\s*(следующий\s+(?:шаг|вопрос)\s*:|вопрос\s*:)\s*.+$")
_NEXT_LINE_DE_RE = re.compile(r"(?im)^\s*(nächste\s+(?:frage|schritt)\s*:)\s*.+$")


def _extract_promille_bucket(diagnostic_summary: str | None) -> str | None:
    if not diagnostic_summary:
        return None
    for ln in [x.strip() for x in diagnostic_summary.splitlines() if x.strip()]:
        low = ln.lower()
        if low.startswith("промилле:") or low.startswith("promille:"):
            val = ln.split(":", 1)[1].strip()
            return val or None
    return None


def _extract_allowed_promille_values(user_content: str, diagnostic_summary: str | None) -> list[str]:
    vals: list[str] = []
    src = (user_content or "") + "\n" + (diagnostic_summary or "")
    for m in _PROMILLE_RANGE_RE.finditer(src):
        for g in (m.group(1), m.group(2)):
            if not g:
                continue
            v = g.replace(",", ".").strip()
            if v and v not in vals:
                vals.append(v)
    return vals


def _extract_last_asked_question(history: list[dict[str, Any]] | None, locale: str) -> str | None:
    if not history:
        return None
    loc = (locale or "de").strip().lower()
    is_ru = loc.startswith("ru")
    is_de = loc.startswith("de")
    for msg in reversed(history):
        if str(msg.get("role") or "").strip().lower() != "assistant":
            continue
        text = str(msg.get("content") or "")
        if not text:
            continue
        safe_lines = []
        for line in text.splitlines():
            t = line.strip()
            if t.startswith("[[DAY_PLAN]]") or t.startswith("[[EVAL]]") or "[[DOSSIER_UPDATE]]" in t:
                continue
            if t.startswith("[[COURSE]]"):
                continue
            safe_lines.append(line)
        safe = "\n".join(safe_lines).strip()
        if not safe:
            continue

        for ln in reversed([x.strip() for x in safe.splitlines() if x.strip()]):
            low = ln.lower()
            if is_ru and (low.startswith("вопрос:") or low.startswith("следующий вопрос:")):
                return ln.split(":", 1)[1].strip() or None
            if is_de and low.startswith("nächste frage:"):
                return ln.split(":", 1)[1].strip() or None
    return None


def _sanitize_hallucinations(
    text: str,
    *,
    locale: str,
    user_content: str,
    diagnostic_summary: str | None,
) -> str:
    """
    Страховка: если модель дорисовала таймлайн/промилле без источника,
    заменяем на плейсхолдеры (для human_text, без dossier).
    """
    out = (text or "").strip()
    if not out:
        return out

    src_user = (user_content or "").strip()
    src_diag = (diagnostic_summary or "").strip()

    allow_time = bool(_TIME_OF_DAY_RE.search(src_user) or _RU_HOUR_RE.search(src_user) or _RELATIVE_TIME_RU_RE.search(src_user))
    allow_time = allow_time or bool(_TIME_OF_DAY_RE.search(src_diag) or _RU_HOUR_RE.search(src_diag) or _RELATIVE_TIME_RU_RE.search(src_diag))

    allow_month = bool(_RU_MONTH_RE.search(src_user) or _RU_MONTH_RE.search(src_diag))

    # 1) время
    if not allow_time:
        out = _TIME_OF_DAY_RE.sub("[время]" if locale == "ru" else "[Uhrzeit]", out)
        out = _RU_HOUR_RE.sub("[время]" if locale == "ru" else "[Uhrzeit]", out)

    # 2) месяц/период
    if locale == "ru" and not allow_month:
        out = _RU_MONTH_PHRASE_RE.sub("[период]", out)

    # 3) промилле: допускаем только те значения, что есть у пользователя/в диагностике.
    allowed_vals = _extract_allowed_promille_values(src_user, diagnostic_summary)
    prom_bucket = _extract_promille_bucket(diagnostic_summary)

    if not allowed_vals and not prom_bucket and not _PROMILLE_WORD_RE.search(src_user) and not _PROMILLE_WORD_RE.search(src_diag):
        out = _PROMILLE_RANGE_RE.sub("[промилле]" if locale == "ru" else "[Promille]", out)
        if locale == "ru":
            out = re.sub(r"\bпромилле\b", "[промилле]", out, flags=re.IGNORECASE)
        return out.strip()

    if prom_bucket:
        out = _PROMILLE_RANGE_RE.sub(prom_bucket, out)
        return out.strip()

    if allowed_vals:

        def _fix(m: re.Match[str]) -> str:
            left = (m.group(1) or "").replace(",", ".").strip()
            right = (m.group(2) or "").replace(",", ".").strip() if m.group(2) else ""
            raw = m.group(0)

            def has_perm(v: str) -> bool:
                return bool(v) and v in allowed_vals

            if has_perm(left) and (not right or has_perm(right)):
                return raw

            suffix = "‰" if "‰" in raw else "промилле"
            return f"{allowed_vals[0]}{suffix}" if suffix == "‰" else f"{allowed_vals[0]} {suffix}"

        out = _PROMILLE_RANGE_RE.sub(_fix, out)

    return out.strip()


def _ensure_next_step_or_question(text: str, *, locale: str, question: str) -> str:
    t = (text or "").rstrip()
    if not t:
        return t

    if locale == "ru":
        if _NEXT_LINE_RU_RE.search(t):
            return t
        return (t + "\n\n" + f"Следующий вопрос: {question}").strip()
    if _NEXT_LINE_DE_RE.search(t):
        return t
    return (t + "\n\n" + f"Nächste Frage: {question}").strip()


def _force_rewrite_step(text: str, *, locale: str, current_question: str) -> str:
    """
    Требуем переписать и вырезаем любые строки со следующими вопросами/шагами,
    чтобы не было дублей из LLM + orchestrator.
    """
    t = (text or "").rstrip()
    if not t:
        t = ""

    if locale == "ru":
        lines = [ln for ln in t.splitlines()]
        cleaned: list[str] = []
        for ln in lines:
            # вырезаем любые "следующий вопрос/вопрос" и любые "следующий шаг"
            if re.match(r"^\s*(следующий\s+вопрос|вопрос)\s*:\s*.+$", ln, flags=re.IGNORECASE):
                continue
            if re.match(r"^\s*следующий\s+шаг\s*:\s*.+$", ln, flags=re.IGNORECASE):
                continue
            cleaned.append(ln)

        base = "\n".join(cleaned).rstrip()
        step = f"Следующий шаг: перепиши ответ на вопрос: {current_question}"
        return (base + "\n\n" + step).strip()

    lines = [ln for ln in t.splitlines()]
    cleaned = []
    for ln in lines:
        if re.match(r"^\s*nächste\s+frage\s*:\s*.+$", ln, flags=re.IGNORECASE):
            continue
        if re.match(r"^\s*nächster\s+schritt\s*:\s*.+$", ln, flags=re.IGNORECASE):
            continue
        cleaned.append(ln)

    base = "\n".join(cleaned).rstrip()
    step = f"Nächster Schritt: Schreibe die Antwort neu zu der Frage: {current_question}"
    return (base + "\n\n" + step).strip()


_CYR_RE = re.compile(r"[А-Яа-яЁё]")
_LAT_RE = re.compile(r"[A-Za-zÄÖÜäöüß]")

def _looks_non_ru_question(q: str) -> bool:
    if not q:
        return False
    # если есть кириллица — это RU/смешанный вопрос, НЕ трогаем
    if _CYR_RE.search(q):
        return False
    # если кириллицы нет, но есть латиница — это не-RU
    return bool(_LAT_RE.search(q))


def process_user_message(db: Session, session_id: UUID, user_content: str, locale: str, mode: str) -> AIMessage:
    repo = Repo(db)

    sess = repo.get_ai_session(session_id)
    if not sess:
        raise APIError("NOT_FOUND", "Session not found", status_code=404)

    content = (user_content or "").strip()
    if not content:
        raise APIError("EMPTY_MESSAGE", "Message is empty", status_code=422)

    loc = (locale or "de").strip().lower()
    if loc.startswith("de"):
        loc = "de"
    elif loc.startswith("ru"):
        loc = "ru"
    else:
        loc = "de"

    m = (mode or "").strip().lower()
    if m not in {"diagnostic", "practice", "mock"}:
        raise APIError("BAD_MODE", "Invalid mode. Use: diagnostic, practice, mock", {"mode": mode}, status_code=422)

    is_boot = content.startswith("[[START_")

    boot_params: dict[str, str] = {}
    if is_boot:
        for m_ in re.finditer(r"\b([a-zA-Z_]+)=([^\s]+)", content):
            boot_params[m_.group(1).strip().lower()] = m_.group(2).strip()
    # Server-side dedup: фронт может ретраить один и тот же POST или отправить двойным кликом.
    # Если это идентичный последнему user-тексту retry, возвращаем уже готовый ответ ассистента.
    if not is_boot:
        try:
            last_user = db.scalar(
                select(AIMessage)
                .where(AIMessage.session_id == session_id, AIMessage.role == "user")
                .order_by(AIMessage.created_at.desc())
                .limit(1)
            )
            if last_user:
                last_assistant = db.scalar(
                    select(AIMessage)
                    .where(AIMessage.session_id == session_id, AIMessage.role == "assistant")
                    .order_by(AIMessage.created_at.desc())
                    .limit(1)
                )

                if _should_reuse_last_assistant_for_same_user_text(
                    incoming_text=content,
                    last_user_text=str(last_user.content or ""),
                    last_user_created_at=last_user.created_at,
                    last_assistant_created_at=(last_assistant.created_at if last_assistant else None),
                    now_utc=datetime.now(timezone.utc),
                ):
                    if last_assistant:
                        return _publicize_ai_message(db, last_assistant)
        except Exception:  # noqa: BLE001
            pass

    user_msg = repo.add_message(session_id, "user", content)

    try:
        tail_rows = repo.list_messages(session_id)[-10:]
        history = [{"role": r.role, "content": r.content} for r in tail_rows]
    except Exception:  # noqa: BLE001
        history = []

    course = _extract_course_state(history)

    # --- COURSE CLOCK SYNC (Europe/Berlin) ---
    # День нельзя перелистнуть: он вычисляется по календарю Europe/Berlin от start_date.
    # Если наступил новый календарный день — автоматически переоткрываем новый день курса.
    if m == "practice" and loc == "ru" and course:
        day_now, start_s, of = _course_clock_sync(course)

        # если start_date был пустой/битый — фиксируем
        if str(course.get("start_date") or "").strip() != start_s:
            course["start_date"] = start_s

        cur_day = int(course.get("day") or 1)
        if cur_day != day_now:
            # новый день наступил -> сбрасываем дневное состояние и показываем интро
            state, qs, plan = _prepare_alcohol_day_state(db, day_int=day_now, of=of, loc=loc, start_date=start_s)
            diagnostic_summary = _build_diagnostic_summary(repo, sess.user_id, loc)
            intro = _render_course_intro_ru(qs, diagnostic_summary=diagnostic_summary)

            dossier_json = json.dumps(
                {"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""},
                ensure_ascii=False, separators=(",", ":"))
            text = (
                    intro
                    + "\n[[DAY_PLAN]]" + json.dumps(plan, ensure_ascii=False, separators=(",", ":"))
                    + "\n[[COURSE]]" + json.dumps(state, ensure_ascii=False, separators=(",", ":"))
                    + "\n[[DOSSIER_UPDATE]]" + dossier_json
            ).strip()

            assistant_msg = repo.add_message(session_id, "assistant", text)
            return _publicize_ai_message(db, assistant_msg)

    # Старт курса (practice): сразу открываем первый вопрос дня (без ручного "да").
    if m == "practice" and is_boot and loc == "ru":
        # День привязан к календарю Europe/Berlin. Пользователь не может перелистнуть.
        start_s = _berlin_today().isoformat()
        day_int = 1
        day_of = 30

        state, qs, plan = _prepare_alcohol_day_state(db, day_int=day_int, of=day_of, loc=loc, start_date=start_s)

        diagnostic_summary = _build_diagnostic_summary(repo, sess.user_id, loc)
        first_q = qs[0] if qs else None
        if first_q:
            state["phase"] = "q"
            lesson = _render_lesson_ru(first_q, 1, len(qs), diagnostic_summary=diagnostic_summary)
            human_text = f"День {day_int}/{day_of}. Начинаем.\n\n{lesson}".strip()
        else:
            human_text = _render_course_intro_ru(qs, diagnostic_summary=diagnostic_summary)

        dossier_json = json.dumps({"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""},
                                  ensure_ascii=False, separators=(",", ":"))
        text = (
                human_text
                + "\n[[DAY_PLAN]]" + json.dumps(plan, ensure_ascii=False, separators=(",", ":"))
                + "\n[[COURSE]]" + json.dumps(state, ensure_ascii=False, separators=(",", ":"))
                + "\n[[DOSSIER_UPDATE]]" + dossier_json
        ).strip()

        assistant_msg = repo.add_message(session_id, "assistant", text)
        return _publicize_ai_message(db, assistant_msg)

    # Fail-safe для фронта: если курс ещё не инициализирован,
    # первый пользовательский текст сразу запускает первый вопрос дня.
    if m == "practice" and loc == "ru" and (not is_boot) and (not course):
        start_s = _berlin_today().isoformat()
        day_int = 1
        day_of = 30

        state, qs, plan = _prepare_alcohol_day_state(db, day_int=day_int, of=day_of, loc=loc, start_date=start_s)
        diagnostic_summary = _build_diagnostic_summary(repo, sess.user_id, loc)
        first_q = qs[0] if qs else None
        if first_q:
            state["phase"] = "q"
            lesson = _render_lesson_ru(first_q, 1, len(qs), diagnostic_summary=diagnostic_summary)
            human_text = f"День {day_int}/{day_of}. Начинаем.\n\n{lesson}".strip()
        else:
            human_text = _render_course_intro_ru(qs, diagnostic_summary=diagnostic_summary)

        dossier_json = json.dumps({"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""}, ensure_ascii=False, separators=(",", ":"))
        text = (
                human_text
                + "\n[[DAY_PLAN]]" + json.dumps(plan, ensure_ascii=False, separators=(",", ":"))
                + "\n[[COURSE]]" + json.dumps(state, ensure_ascii=False, separators=(",", ":"))
                + "\n[[DOSSIER_UPDATE]]" + dossier_json
        ).strip()

        assistant_msg = repo.add_message(session_id, "assistant", text)
        return _publicize_ai_message(db, assistant_msg)

    # Подтверждение старта: пользователь пишет "да" -> выдаём урок по вопросу 1
    if m == "practice" and loc == "ru" and course and course.get("phase") == "intro":
        if loc == "ru" and (_course_yes(content, loc) or _course_start_intent(content, loc)):
            keys = course.get("keys") or []
            i = int(course.get("i") or 0)
            q = OFFICIAL_ALCOHOL.get(keys[i]) if i < len(keys) else None
            if q:
                course["phase"] = "q"
                diagnostic_summary = _build_diagnostic_summary(repo, sess.user_id, loc)
                lesson = _render_lesson_ru(q, i + 1, len(keys), diagnostic_summary=diagnostic_summary)
                dossier_json = json.dumps({"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""}, ensure_ascii=False, separators=(",", ":"))
                text = (lesson + "\n[[COURSE]]" + json.dumps(course, ensure_ascii=False, separators=(",", ":")) + "\n[[DOSSIER_UPDATE]]" + dossier_json).strip()
                assistant_msg = repo.add_message(session_id, "assistant", text)
                return _publicize_ai_message(db, assistant_msg)

        # если не "да" — повторяем коротко
        retry = "Ок. Если готов начать вопросы — ответь «да»." if loc == "ru" else "Wenn du starten willst, antworte „Ja“."
        dossier_json = json.dumps({"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""}, ensure_ascii=False, separators=(",", ":"))
        text = (retry + "\n[[COURSE]]" + json.dumps(course, ensure_ascii=False, separators=(",", ":")) + "\n[[DOSSIER_UPDATE]]" + dossier_json).strip()
        assistant_msg = repo.add_message(session_id, "assistant", text)
        return _publicize_ai_message(db, assistant_msg)

    ev: dict[str, Any] = {}
    if not is_boot:
        ev = evaluate_user_message(content) or {}
        repo.add_evaluation(
            session_id=session_id,
            message_id=user_msg.id,
            rubric_scores=ev.get("rubric_scores") or {},
            summary_feedback=str(ev.get("summary_feedback") or ""),
            detected_issues=ev.get("detected_issues") or {},
        )

    # --- COURSE: pressure drill stage (no LLM) ---
    # After an accepted official answer in the daily course we run a short "pressure" drill:
    # 1) one уточняющий вопрос без подсказок (как на интервью),
    # 2) короткий ответ 2–4 предложения,
    # 3) затем следующий официальный вопрос / закрытие дня.
    if (not is_boot) and m == "practice" and loc == "ru" and course and course.get("phase") == "pressure":
        p_q = str(course.get("p_q") or "").strip() or _pick_pressure_drill_ru(str(course.get("p_key") or ""))
        if _too_short_pressure_answer_ru(content):
            human_text = (
                "Ответ на стресс-вопрос слишком короткий. Сейчас нужно 2–4 предложения: факты → ответственность → барьер/альтернатива.\n\n"
                "Стресс-вопрос:\n"
                f"{p_q}"
            ).strip()

            blocks: list[str] = []
            if isinstance(ev, dict) and ev.get("rubric_scores") is not None:
                flags_obj = (((ev.get("detected_issues") or {}).get("flags") or {}) if isinstance(ev.get("detected_issues"), dict) else {})
                eval_block = {"rubric": ev.get("rubric_scores") or {}, "summary": str(ev.get("summary_feedback") or ""), "flags": flags_obj}
                blocks.append("[[EVAL]]" + json.dumps(eval_block, ensure_ascii=False, separators=(",", ":")))

            # Keep course state + empty dossier update
            course["p_q"] = p_q
            blocks.append("[[COURSE]]" + json.dumps(course, ensure_ascii=False, separators=(",", ":")))

            dossier_json = json.dumps({"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""}, ensure_ascii=False, separators=(",", ":"))

            final = human_text
            if blocks:
                final = (final + "\n" + "\n".join(blocks)).strip()
            final = (final + "\n[[DOSSIER_UPDATE]]" + dossier_json).strip()

            assistant_msg = repo.add_message(session_id, "assistant", final)
            return _publicize_ai_message(db, assistant_msg)

        # accepted pressure answer -> короткий дебриф и следующий этап
        diagnostic_summary = _build_diagnostic_summary(repo, sess.user_id, loc)

        base = (
            "Ок. Принято.\n"
            "Короткий разбор: в стресс-режиме держи 3 вещи — 1 факт, 1 ответственность, 1 барьер/альтернатива."
        ).strip()

        # clean pressure fields
        try:
            course.pop("p_key", None)
            course.pop("p_q", None)
        except Exception:
            pass

        keys = course.get("keys") or []
        i = int(course.get("i") or 0)

        # прошли последний вопрос дня -> выдаём домашку и закрываем день окончательно после ответа
        if i >= (len(keys) - 1):
            wrap = [
                f"День {int(course.get('day') or 1)}/{int(course.get('of') or 30)} завершён.",
                "Что важно закрепить: факты/таймлайн → ответственность → изменения/барьеры.",
                "",
                "Теперь можешь задавать любые вопросы, которые могут быть на MPU — я подскажу, как правильно отвечать.",
                "Пример: «Как объяснить, почему я тогда сел за руль?», «Что говорить про триггеры на алкоголь?»",
                "",
                "Приходи завтра.",
            ]
            course["phase"] = "qa"
            human_text = (base + "\n\n" + "\n".join(wrap)).strip()
        else:
            course["i"] = i + 1
            course["phase"] = "q"
            next_q = OFFICIAL_ALCOHOL.get(keys[course["i"]]) if course.get("i") is not None and course["i"] < len(keys) else None
            if next_q:
                lesson = _render_lesson_ru(next_q, course["i"] + 1, len(keys), diagnostic_summary=diagnostic_summary)
                human_text = (base + "\n\n" + lesson).strip()
            else:
                human_text = base

        blocks: list[str] = []
        if isinstance(ev, dict) and ev.get("rubric_scores") is not None:
            flags_obj = (((ev.get("detected_issues") or {}).get("flags") or {}) if isinstance(ev.get("detected_issues"), dict) else {})
            eval_block = {"rubric": ev.get("rubric_scores") or {}, "summary": str(ev.get("summary_feedback") or ""), "flags": flags_obj}
            blocks.append("[[EVAL]]" + json.dumps(eval_block, ensure_ascii=False, separators=(",", ":")))

        blocks.append("[[COURSE]]" + json.dumps(course, ensure_ascii=False, separators=(",", ":")))

        dossier_json = json.dumps({"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""}, ensure_ascii=False, separators=(",", ":"))

        final = human_text.strip()
        if blocks:
            final = (final + "\n" + "\n".join(blocks)).strip()
        final = (final + "\n[[DOSSIER_UPDATE]]" + dossier_json).strip()

        assistant_msg = repo.add_message(session_id, "assistant", final)
        return _publicize_ai_message(db, assistant_msg)

    # --- COURSE: free questions after day is closed (uses LLM) ---
    # After finishing the day, user can ask any MPU-related question.
    if (not is_boot) and m == "practice" and loc == "ru" and course and course.get("phase") == "qa":
        q = (content or "").strip()
        low = q.lower()

        # allow user to end Q&A explicitly
        if low in {"закончить", "стоп", "выход"}:
            day = int(course.get("day") or 1)
            of = int(course.get("of") or 30)
            course["phase"] = "done"
            human_text = (
                f"Ок. День {day}/{of} закрыт.\n"
                "Если появятся вопросы — просто напиши их сюда."
            ).strip()
        else:
            if not q:
                human_text = "Напиши любой вопрос, который может быть на MPU — и я подскажу, как правильно отвечать.".strip()
            else:
                diagnostic_summary = _build_diagnostic_summary(repo, sess.user_id, loc)
                human_text = generate_free_question_reply(
                    question_text=q,
                    locale=loc,
                    diagnostic_summary=diagnostic_summary,
                    diagnostic_facts=None,
                    include_stress_question=False,
                ).strip()

        blocks = ["[[COURSE]]" + json.dumps(course, ensure_ascii=False, separators=(",", ":"))]
        dossier_json = json.dumps({"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""},
                                  ensure_ascii=False, separators=(",", ":"))
        final = (human_text + "\n" + "\n".join(blocks) + "\n[[DOSSIER_UPDATE]]" + dossier_json).strip()
        assistant_msg = repo.add_message(session_id, "assistant", final)
        return _publicize_ai_message(db, assistant_msg)

        # accept homework -> close day finally
        day = int(course.get("day") or 1)
        of = int(course.get("of") or 30)
        course["phase"] = "done"
        course.pop("hw_q", None)

        human_text = (
            "Ок. Принято.\n"
            "Короткий разбор: держи 3 вещи — факт/таймлайн → ответственность → барьер.\n\n"
            f"Домашка принята. День {day}/{of} закрыт окончательно."
        ).strip()

        blocks = ["[[COURSE]]" + json.dumps(course, ensure_ascii=False, separators=(",", ":"))]
        dossier_json = json.dumps({"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""},
                                  ensure_ascii=False, separators=(",", ":"))
        final = (human_text + "\n" + "\n".join(blocks) + "\n[[DOSSIER_UPDATE]]" + dossier_json).strip()
        assistant_msg = repo.add_message(session_id, "assistant", final)
        return _publicize_ai_message(db, assistant_msg)

    # --- COURSE: day already closed ---
    if (not is_boot) and m == "practice" and loc == "ru" and course and course.get("phase") == "done":
        # UX: allow plain-text "Начать обучение" from UI to immediately open next day.
        if _course_start_intent(content, loc):
            day = int(course.get("day") or 1)
            of = int(course.get("of") or 30)
            start_s = str(course.get("start_date") or _berlin_today().isoformat())
            next_day = min(max(1, day + 1), max(1, of))

            state, qs, plan = _prepare_alcohol_day_state(db, day_int=next_day, of=of, loc=loc, start_date=start_s)
            diagnostic_summary = _build_diagnostic_summary(repo, sess.user_id, loc)
            first_q = qs[0] if qs else None
            if first_q:
                state["phase"] = "q"
                lesson = _render_lesson_ru(first_q, 1, len(qs), diagnostic_summary=diagnostic_summary)
                human_text = f"День {next_day}/{of}. Начинаем.\n\n{lesson}".strip()
            else:
                human_text = _render_course_intro_ru(qs, diagnostic_summary=diagnostic_summary)

            dossier_json = json.dumps({"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""},
                                      ensure_ascii=False, separators=(",", ":"))
            text = (
                    human_text
                    + "\n[[DAY_PLAN]]" + json.dumps(plan, ensure_ascii=False, separators=(",", ":"))
                    + "\n[[COURSE]]" + json.dumps(state, ensure_ascii=False, separators=(",", ":"))
                    + "\n[[DOSSIER_UPDATE]]" + dossier_json
            ).strip()

            assistant_msg = repo.add_message(session_id, "assistant", text)
            return _publicize_ai_message(db, assistant_msg)

        day = int(course.get("day") or 1)
        of = int(course.get("of") or 30)
        human_text = (
            f"День {day}/{of} уже закрыт.\n"
            "Чтобы начать следующий день — нажми «Начать обучение» в кабинете."
        ).strip()

        blocks = ["[[COURSE]]" + json.dumps(course, ensure_ascii=False, separators=(",", ":"))]
        dossier_json = json.dumps({"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""},
                                  ensure_ascii=False, separators=(",", ":"))
        final = (human_text + "\n" + "\n".join(blocks) + "\n[[DOSSIER_UPDATE]]" + dossier_json).strip()
        assistant_msg = repo.add_message(session_id, "assistant", final)
        return _publicize_ai_message(db, assistant_msg)

    # BOOT: стартуем без LLM
    if is_boot and m in {"practice", "mock"}:
        intro = _boot_message(loc, m)
        q = _start_question(loc)

        blocks: list[str] = []
        if m == "practice":
            day_raw = boot_params.get("day") or ""
            try:
                day_int = int(day_raw.split("/")[0]) if day_raw else 1
            except Exception:  # noqa: BLE001
                day_int = 1
            focus = (boot_params.get("focus") or "").strip()
            plan = {
                "day": day_int,
                "title": "План дня" if loc == "ru" else "Tagesplan",
                "agenda": [
                    "Факты и таймлайн (без воды)" if loc == "ru" else "Fakten & Zeitlinie (ohne Ausschmückung)",
                    "Ответственность (без оправданий)" if loc == "ru" else "Verantwortung (ohne Rechtfertigungen)",
                    "Одна конкретная мера/правило на сегодня" if loc == "ru" else "Eine konkrete Maßnahme/Regel für heute",
                ],
                "success_criteria": [
                    "В ответе есть когда/где/что" if loc == "ru" else "Antwort enthält wann/wo/was",
                    "Есть фраза ответственности (я сделал/я решил)"
                    if loc == "ru"
                    else "Klare Verantwortung (ich habe entschieden/ich habe getan)",
                    "Есть один измеримый шаг" if loc == "ru" else "Ein messbarer Schritt",
                ],
                "timebox_min": 20,
                "focus": focus,
            }
            blocks.append("[[DAY_PLAN]]" + json.dumps(plan, ensure_ascii=False, separators=(",", ":")))

        dossier_json = json.dumps({"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""}, ensure_ascii=False, separators=(",", ":"))

        text = f"{intro}\nВопрос: {q}" if loc == "ru" else f"{intro}\nNächste Frage: {q}"
        if blocks:
            text = (text + "\n" + "\n".join(blocks)).strip()
        text = (text + "\n[[DOSSIER_UPDATE]]" + dossier_json).strip()

        assistant_msg = repo.add_message(session_id, "assistant", text)
        return _publicize_ai_message(db, assistant_msg)

    # ЖЁСТКИЙ ГЕЙТ: короткий ответ
    if (not is_boot) and m in {"practice", "mock"} and _too_short_for_training(content):
        cur_q = _extract_last_asked_question(history, loc)
        cur_key = _match_official_key_ru(cur_q) if loc == "ru" else None
        human_text = _clarify_message(loc, m, key=cur_key, question=cur_q)

        blocks: list[str] = []
        if ev.get("rubric_scores") is not None:
            flags_obj = (((ev.get("detected_issues") or {}).get("flags") or {}) if isinstance(ev.get("detected_issues"), dict) else {})
            eval_block = {"rubric": ev.get("rubric_scores") or {}, "summary": str(ev.get("summary_feedback") or ""), "flags": flags_obj}
            blocks.append("[[EVAL]]" + json.dumps(eval_block, ensure_ascii=False, separators=(",", ":")))

        dossier_json = json.dumps({"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""}, ensure_ascii=False, separators=(",", ":"))

        final = human_text.strip()
        if blocks:
            final = (final + "\n" + "\n".join(blocks)).strip()
        final = (final + "\n[[DOSSIER_UPDATE]]" + dossier_json).strip()

        assistant_msg = repo.add_message(session_id, "assistant", final)
        return _publicize_ai_message(db, assistant_msg)

    topic_id: UUID | None = None
    try:
        case = repo.get_route_case(sess.user_id)
        if case:
            topic_id = _extract_topic_id(db, case)
    except Exception:  # noqa: BLE001
        topic_id = None

    required_tags: list[str] = []
    flags = ((ev.get("detected_issues") or {}).get("flags") or {}) if isinstance(ev, dict) else {}

    if flags.get("missing_timeline"):
        required_tags += ["timeline", "facts"]
    if flags.get("blame_shift"):
        required_tags += ["responsibility"]
    if flags.get("missing_actions"):
        required_tags += ["plan", "prevention", "strategy"]

    required_tags = list(dict.fromkeys([t for t in required_tags if t]))

    course = _extract_course_state(history)

    if m == "practice" and loc == "ru" and course and course.get("phase") == "q":
        keys = course.get("keys") or []
        i = int(course.get("i") or 0)
        cur_key = keys[i] if i < len(keys) else ""
        qobj = OFFICIAL_ALCOHOL.get(cur_key)
        question = qobj.question_ru if qobj else next_question(db, locale=loc, mode=m, topic_id=topic_id, required_tags=required_tags or None)
    else:
        question = next_question(db, locale=loc, mode=m, topic_id=topic_id, required_tags=required_tags or None)
    # страховка: если по какой-то причине прилетела не-RU строка
    if loc == "ru" and _looks_non_ru_question(question) and not (
            m == "practice" and course and course.get("phase") == "q"):
        translated = translate_question_to_ru(question)
        if translated and translated.strip() and not _looks_non_ru_question(translated):
            question = translated.strip()
        else:
            question = "Что стало решающим моментом, из-за которого ты всё равно сел за руль, и какие альтернативы были доступны?"

    diagnostic_summary = _build_diagnostic_summary(repo, sess.user_id, loc)
    diagnostic_facts = _build_diagnostic_facts(repo, sess.user_id, loc)

    course_context: dict[str, Any] | None = None
    if m == "practice" and loc == "ru" and course and course.get("phase") == "q":
        keys = course.get("keys") or []
        i = int(course.get("i") or 0)
        cur_key = keys[i] if i < len(keys) else ""
        qobj_ctx = OFFICIAL_ALCOHOL.get(cur_key)
        if qobj_ctx:
            course_context = {
                "key": qobj_ctx.key,
                "question_ru": qobj_ctx.question_ru,
                "source": qobj_ctx.source,
                "essence_ru": qobj_ctx.essence_ru,
                "want_ru": qobj_ctx.want_ru,
                "avoid_ru": qobj_ctx.avoid_ru,
                "skeleton_ru": qobj_ctx.skeleton_ru,
                "day": course.get("day"),
                "of": course.get("of"),
                "module": course.get("module"),
            }

    assistant_text = generate_assistant_reply(
        mode=m,
        question=question,
        user_answer=content,
        locale=loc,
        diagnostic_summary=diagnostic_summary,
        diagnostic_facts=diagnostic_facts,
        course_context=course_context,
        history=history,
        rubric_scores=ev.get("rubric_scores") if isinstance(ev, dict) else None,
        summary_feedback=str(ev.get("summary_feedback") or "") if isinstance(ev, dict) else "",
        detected_issues=ev.get("detected_issues") if isinstance(ev, dict) else None,
    )

    marker = "[[DOSSIER_UPDATE]]"
    assistant_raw = (assistant_text or "").strip()

    dossier_json = "{}"
    human_text = assistant_raw

    if marker in assistant_raw:
        i = assistant_raw.index(marker)
        human_text = assistant_raw[:i].rstrip()
        dossier_json = assistant_raw[i + len(marker) :].strip() or "{}"

    try:
        obj = json.loads(dossier_json)
        if not isinstance(obj, dict):
            raise ValueError("dossier must be dict")
    except Exception:  # noqa: BLE001
        dossier_json = json.dumps({"reason": "", "responsibility": "", "changes": "", "shortStory": "", "redZones": ""}, ensure_ascii=False, separators=(",", ":"))

    # server-side safety: убираем дорисованные детали
    human_text = _sanitize_hallucinations(human_text, locale=loc, user_content=content, diagnostic_summary=diagnostic_summary)

    # --- Двухпроходная логика practice: первый раз всегда просим переписать по исправленному варианту ---
    prev_rewrite = False
    if history:
        for msg in reversed(history):
            if str(msg.get("role") or "").strip().lower() == "assistant":
                t = str(msg.get("content") or "").lower()
                prev_rewrite = ("перепиши ответ" in t) or ("следующий шаг" in t and "перепиши" in t)
                break

    is_course_q = (m == "practice" and loc == "ru" and course and course.get("phase") == "q")
    cur_course_key = ""
    course_need_rewrite = False
    if is_course_q:
        keys = course.get("keys") or []
        i = int(course.get("i") or 0)
        cur_course_key = keys[i] if i < len(keys) else ""
        course_need_rewrite = _course_needs_rewrite(flags, cur_course_key, content)

    in_daily_course = bool(course and course.get("phase") in {"intro", "q", "pressure", "qa", "done"})
    # "rewrite on first pass" is only for generic practice, not for the daily course state machine.
    force_rewrite_first_pass = (m == "practice" and (not is_boot) and (not prev_rewrite) and (not is_course_q) and (not in_daily_course))

    enforce_rewrite = False
    if m == "practice":
        if is_course_q:
            enforce_rewrite = bool(course_need_rewrite)
        else:
            enforce_rewrite = bool(flags.get("missing_timeline") or flags.get("missing_actions") or flags.get("blame_shift") or force_rewrite_first_pass)

    # enforce training policy
    if m == "practice" and enforce_rewrite:
        cur_q = _extract_last_asked_question(history, loc) or (_start_question(loc) if loc == "ru" else _start_question("de"))
        human_text = _force_rewrite_step(human_text, locale=loc, current_question=cur_q)
    else:
        if not (m == "practice" and loc == "ru" and course and course.get("phase") in {"q", "pressure", "done"}):
            human_text = _ensure_next_step_or_question(human_text, locale=loc, question=question)

    need_rewrite = (m == "practice" and enforce_rewrite)

    # COURSE: accepted official answer -> сразу короткий "pressure" уточняющий вопрос (без подсказок).
    # Переход к следующему официальному вопросу/закрытие дня делаем только после ответа на pressure.
    if m == "practice" and loc == "ru" and (not need_rewrite) and course and course.get("phase") == "q":
        keys = course.get("keys") or []
        i = int(course.get("i") or 0)
        cur_key = keys[i] if i < len(keys) else ""
        p_q = _pick_pressure_drill_ru(cur_key, seed=(int(course.get("day") or 0) * 100 + i))

        # не даём модели перескакивать дальше
        human_text = re.sub(r"(?im)^\s*(следующий вопрос|вопрос)\s*:\s*.*\n?", "", human_text).strip()

        course["phase"] = "pressure"
        course["p_key"] = cur_key
        course["p_q"] = p_q

        pressure_block = (
            "Стресс-вопрос (как на интервью, без подсказок):\n"
            f"{p_q}\n"
            "Ответь 2–4 предложениями: факты → ответственность → барьер/альтернатива."
        )
        human_text = (human_text + "\n\n" + pressure_block).strip()

    blocks: list[str] = []
    if isinstance(ev, dict) and "rubric_scores" in ev:
        if "[[EVAL]]" not in assistant_raw:
            flags_obj = ((ev.get("detected_issues") or {}).get("flags") or {})
            eval_block = {"rubric": ev.get("rubric_scores") or {}, "summary": str(ev.get("summary_feedback") or ""), "flags": flags_obj}
            blocks.append("[[EVAL]]" + json.dumps(eval_block, ensure_ascii=False, separators=(",", ":")))

    if m == "practice" and course:
        blocks.append("[[COURSE]]" + json.dumps(course, ensure_ascii=False, separators=(",", ":")))

    final = human_text.strip()
    if blocks:
        final = (final + "\n" + "\n".join(blocks)).strip()
    final = (final + "\n" + marker + dossier_json).strip()

    assistant_msg = repo.add_message(session_id, "assistant", final)

    return _publicize_ai_message(db, assistant_msg)
