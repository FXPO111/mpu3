from __future__ import annotations

import re
from dataclasses import dataclass

_VAGUE_WORDS = {
    "maybe",
    "probably",
    "perhaps",
    "somehow",
    "kind of",
    "sort of",
    "i guess",
    "вроде",
    "как бы",
    "наверное",
    "возможно",
    "типа",
    "ну",
    "короче",
    "как-то",
    "irgendwie",
    "vielleicht",
    "sozusagen",
    "quasi",
}

_BLAME_SHIFT = {
    "they made me",
    "it was their fault",
    "not my fault",
    "forced me",
    "меня заставили",
    "они виноваты",
    "не моя вина",
    "виноваты они",
    "ich konnte nichts dafür",
    "die anderen",
    "die schuld liegt",
}

_RESPONSIBILITY_MARKERS = {
    "i did",
    "i decided",
    "i chose",
    "i take responsibility",
    "i was wrong",
    "я сделал",
    "я решил",
    "я выбирал",
    "я беру ответственность",
    "я был неправ",
    "ich habe",
    "ich entschied",
    "ich übernehme verantwortung",
    "ich habe einen fehler gemacht",
}

_ACTION_VERBS = {
    "stopped",
    "quit",
    "changed",
    "started",
    "learned",
    "planned",
    "scheduled",
    "attend",
    "перестал",
    "бросил",
    "изменил",
    "начал",
    "выучил",
    "планирую",
    "записался",
    "посещаю",
    "aufgehört",
    "geändert",
    "begonnen",
    "gelernt",
    "plane",
    "habe mich angemeldet",
}

_TIME_HINTS = {
    "yesterday",
    "today",
    "tomorrow",
    "last",
    "since",
    "month",
    "week",
    "year",
    "вчера",
    "сегодня",
    "завтра",
    "прошл",
    "с",
    "недел",
    "месяц",
    "год",
    "gestern",
    "heute",
    "morgen",
    "seit",
    "woche",
    "monat",
    "jahr",
}

_MONTHS = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "январ",
    "феврал",
    "март",
    "апрел",
    "май",
    "июн",
    "иююл",
    "август",
    "сентябр",
    "октябр",
    "ноябр",
    "декабр",
    "januar",
    "februar",
    "märz",
    "april",
    "mai",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "dezember",
}

_CONTRADICTION_PAIRS = [
    ("never", "sometimes"),
    ("always", "sometimes"),
    ("never", "often"),
    ("никогда", "иногда"),
    ("всегда", "иногда"),
    ("никогда", "часто"),
    ("nie", "manchmal"),
    ("immer", "manchmal"),
]


@dataclass
class _Signals:
    word_count: int
    has_numbers: bool
    has_time: bool
    has_place_like: bool
    has_actions: bool
    responsibility: bool
    blame_shift: bool
    vagueness: bool
    contradictions: list[str]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _tokenize(s: str) -> list[str]:
    # keep letters/digits, split everything else
    return [t for t in re.split(r"[^a-zA-Z0-9À-žА-Яа-яІіЇїЄєҐґ]+", s) if t]


def _detect_signals(content: str) -> _Signals:
    txt = _norm(content)
    tokens = _tokenize(txt)
    word_count = len(tokens)

    has_numbers = bool(re.search(r"\d", txt))
    has_month = any(m in txt for m in _MONTHS)
    has_time_hint = any(h in txt for h in _TIME_HINTS)
    has_time = has_numbers or has_month or has_time_hint

    # very rough "place-like": mentions city/country words or patterns "in Berlin", "в Киеве"
    has_place_like = bool(re.search(r"\b(in|at|в|у|bei)\b\s+[A-ZÀ-ŽА-ЯІЇЄҐ]", content)) or bool(
        re.search(r"\b(berlin|hamburg|münchen|munich|köln|cologne|kyiv|kiev|frankfurt)\b", txt)
    )

    has_actions = any(v in txt for v in _ACTION_VERBS)
    responsibility = any(m in txt for m in _RESPONSIBILITY_MARKERS)
    blame_shift = any(b in txt for b in _BLAME_SHIFT)

    vagueness = any(w in txt for w in _VAGUE_WORDS)

    contradictions: list[str] = []
    for a, b in _CONTRADICTION_PAIRS:
        if a in txt and b in txt:
            contradictions.append(f"'{a}' vs '{b}'")

    return _Signals(
        word_count=word_count,
        has_numbers=has_numbers,
        has_time=has_time,
        has_place_like=has_place_like,
        has_actions=has_actions,
        responsibility=responsibility,
        blame_shift=blame_shift,
        vagueness=vagueness,
        contradictions=contradictions,
    )


def _clamp_0_5(x: int) -> int:
    return 0 if x < 0 else 5 if x > 5 else x


def evaluate_user_message(content: str) -> dict:
    """
    Heuristic rubric scoring for MPU training.

    Returns:
      {
        "rubric_scores": {"clarity": 0..5, "specificity": 0..5, "consistency": 0..5, "responsibility": 0..5},
        "summary_feedback": str,
        "detected_issues": {"contradictions": [...], "flags": {...}}
      }
    """
    s = _detect_signals(content)

    # Clarity: penalize too short or very long unstructured text (word count heuristic)
    if s.word_count < 10:
        clarity = 1
    elif s.word_count < 25:
        clarity = 3
    elif s.word_count < 80:
        clarity = 4
    else:
        clarity = 3  # long answers often drift without structure
    if s.vagueness:
        clarity -= 1
    clarity = _clamp_0_5(clarity)

    # Specificity: time + numbers + place + concrete actions
    specificity = 1
    if s.has_time:
        specificity += 1
    if s.has_numbers:
        specificity += 1
    if s.has_place_like:
        specificity += 1
    if s.has_actions:
        specificity += 1
    if s.vagueness:
        specificity -= 1
    specificity = _clamp_0_5(specificity)

    # Responsibility: explicit ownership + concrete change; penalize blame shifting
    responsibility = 2
    if s.responsibility:
        responsibility += 2
    if s.has_actions:
        responsibility += 1
    if s.blame_shift:
        responsibility -= 2
    responsibility = _clamp_0_5(responsibility)

    # Consistency: without history we can only detect self-contradiction markers
    consistency = 4
    if s.vagueness:
        consistency -= 1
    if s.contradictions:
        consistency -= 2
    consistency = _clamp_0_5(consistency)

    rubric_scores = {
        "clarity": clarity,
        "specificity": specificity,
        "consistency": consistency,
        "responsibility": responsibility,
    }

    flags = {
        "too_short": s.word_count < 10,
        "vague_language": s.vagueness,
        "missing_timeline": not s.has_time,
        "missing_actions": not s.has_actions,
        "blame_shift": s.blame_shift,
        "contradiction_markers": bool(s.contradictions),
    }

    # Feedback (short, actionable)
    bullets = []
    if flags["too_short"]:
        bullets.append("Add 2–3 concrete facts (what/when/where).")
    if flags["missing_timeline"]:
        bullets.append("Include timeline (date/month/period).")
    if flags["missing_actions"]:
        bullets.append("State what you did to change the situation (specific steps).")
    if flags["blame_shift"]:
        bullets.append("Avoid shifting blame; emphasize your responsibility and decisions.")
    if flags["vague_language"]:
        bullets.append("Remove vague wording; be specific and measurable.")
    if flags["contradiction_markers"]:
        bullets.append("Your wording contains contradiction markers; keep statements consistent.")

    if not bullets:
        feedback = "Solid answer. Keep it factual, time-bound, and focused on your responsibility and concrete changes."
    else:
        feedback = " | ".join(bullets[:4])

    return {
        "rubric_scores": rubric_scores,
        "summary_feedback": feedback,
        "detected_issues": {
            "contradictions": s.contradictions,
            "flags": flags,
        },
    }
