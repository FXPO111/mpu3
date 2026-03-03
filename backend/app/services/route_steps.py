from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Step:
    id: str
    prompt: str
    input_type: str  # text|yes_no|date_or_month|number|tags
    required: bool
    write_path: str  # dot path into case.data_json
    show_if: Callable[[dict], bool] | None = None


def _get(d: dict, path: str, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def steps_for_topic(topic: str) -> list[Step]:
    # base (всегда)
    base: list[Step] = [
        Step("topic_confirm", "Тема MPU? (alcohol/drugs/points/incident)", "text", True, "meta.topic"),
        Step("incident_date", "Дата инцидента (если не помнишь — месяц/год)", "date_or_month", True, "incident.date"),
        Step("incident_summary", "Коротко: что произошло (1–2 предложения)", "text", True, "incident.summary"),
        Step("test_done", "Был тест/анализ? (да/нет)", "yes_no", True, "incident.test.done"),
        Step(
            "test_result",
            "Результат теста (как в бумаге, можно текстом)",
            "text",
            True,
            "incident.test.result",
            show_if=lambda data: _get(data, "incident.test.done") is True,
        ),
        Step("prior_cases", "Было раньше что-то похожее? (да/нет)", "yes_no", True, "history.prior_cases"),
        Step("last_use_date", "Последнее употребление (дата/примерно)", "date_or_month", True, "use.last_date"),
        Step("changes_3", "3 конкретных изменения после инцидента (через запятую)", "tags", True, "changes.list"),
        Step("triggers_3", "3 триггера (через запятую)", "tags", True, "risk.triggers"),
        Step("stop_protocol", "Что делаешь в первые 30 минут, если накрывает? (по шагам)", "text", True, "plan.stop_30min"),
    ]

    t = (topic or "unknown").strip().lower()

    if t == "alcohol":
        return base + [
            Step("alcohol_promille", "Промилле/результат алкоголя (если неизвестно — оставь пусто)", "text", False, "alcohol.promille"),
            Step("alcohol_pattern", "Как часто пил до инцидента? (дни/объём, коротко)", "text", True, "alcohol.pattern"),
        ]

    if t == "drugs":
        return base + [
            Step("drug_type", "Какие вещества? (конкретно)", "text", True, "drugs.type"),
            Step("drug_pattern", "Как часто/в каких ситуациях употреблял?", "text", True, "drugs.pattern"),
        ]

    if t == "points":
        return base + [
            Step("points_reason", "За что набрались пункты? (типы нарушений)", "text", True, "points.reason"),
            Step("points_pattern", "Повторяющийся паттерн? (скорость/телефон/агрессия/...)", "text", True, "points.pattern"),
        ]

    if t == "incident":
        return base + [
            Step("incident_trigger", "Что было триггером инцидента?", "text", True, "incident.trigger"),
            Step("incident_change", "Что сделал, чтобы это не повторилось? (конкретно)", "text", True, "incident.change"),
        ]

    return base