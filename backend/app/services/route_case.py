from __future__ import annotations

from typing import Any

from app.services.route_steps import steps_for_topic


def _set_path(d: dict, path: str, value: Any) -> None:
    cur = d
    parts = path.split(".")
    for k in parts[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[k] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _parse_value(input_type: str, raw: Any) -> Any:
    if input_type == "yes_no":
        if isinstance(raw, bool):
            return raw
        s = str(raw).strip().lower()
        if s in {"да", "yes", "y", "true", "1"}:
            return True
        if s in {"нет", "no", "n", "false", "0"}:
            return False
        raise ValueError("Expected yes/no")

    if input_type == "tags":
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        s = str(raw).strip()
        return [t.strip() for t in s.split(",") if t.strip()]

    if input_type in {"text", "date_or_month", "number"}:
        return str(raw).strip()

    return raw


def get_next_step(topic: str, data_json: dict, setup_step: int) -> tuple[int, dict | None, int]:
    steps = steps_for_topic(topic)
    total = len(steps)

    i = max(0, int(setup_step))
    while i < total:
        st = steps[i]
        if st.show_if is None or st.show_if(data_json):
            return i, {
                "step_id": st.id,
                "prompt": st.prompt,
                "input": {"type": st.input_type, "required": st.required},
            }, total
        i += 1

    return total, None, total


def apply_answer(case, step_id: str, value_raw: Any) -> None:
    steps = steps_for_topic(case.topic)
    st = next((x for x in steps if x.id == step_id), None)
    if not st:
        raise ValueError("Unknown step_id")

    # required
    if st.required and (value_raw is None or str(value_raw).strip() == ""):
        raise ValueError("Value required")

    # optional skip
    if value_raw is None or str(value_raw).strip() == "":
        return

    value = _parse_value(st.input_type, value_raw)

    data = dict(case.data_json or {})
    _set_path(data, st.write_path, value)

    # topic_confirm can change case.topic
    if step_id == "topic_confirm":
        t = str(value).strip().lower()
        if t in {"alcohol", "drugs", "points", "incident"}:
            case.topic = t
            case.setup_step = 0
        _set_path(data, "meta.topic", t)

    case.data_json = data