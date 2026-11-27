"""Redacted projection of a fixed 24-hour hotspot voucher history read."""
from __future__ import annotations

from collections.abc import Mapping


_INT32_MAX = 2**31 - 1
_INT64_MAX = 2**63 - 1
_MAX_USAGE_ROWS = 500
_SUMMARY_FIELDS = {"count", "duration", "amount", "currency"}
_USAGE_FIELDS = {"count", "timeInterval", "time", "amount", "currency"}
_MISSING = object()


class VoucherHistoryStatisticsError(ValueError):
    pass


def _int_state(value: object, maximum: int, minimum: int = 0) -> str:
    if value is _MISSING:
        return "missing"
    if value is None:
        return "null"
    if type(value) is int and minimum <= value <= maximum:
        return "present"
    return "invalid"


def _unknown_count(value: Mapping[object, object], known: set[str]) -> int:
    return sum(1 for key in value if not isinstance(key, str) or key not in known)


def summarize_voucher_history_statistics(raw: object) -> dict[str, object]:
    """Project documented counters while discarding money and time-series values."""
    if not isinstance(raw, Mapping):
        raise VoucherHistoryStatisticsError("result_invalid")

    unknown_fields = _unknown_count(raw, {"summary", "usage"})
    summary = raw.get("summary", _MISSING)
    summary_state = ("missing" if summary is _MISSING else
                     "null" if summary is None else
                     "present" if isinstance(summary, Mapping) else "invalid")
    if isinstance(summary, Mapping):
        unknown_fields += _unknown_count(summary, _SUMMARY_FIELDS)
    else:
        summary = {}

    metrics: dict[str, int | None] = {}
    metric_states: dict[str, str] = {}
    missing_fields: list[str] = []
    invalid_fields: list[str] = []
    for field, output, maximum in (
            ("count", "voucher_count", _INT64_MAX),
            ("duration", "voucher_duration_minutes", _INT64_MAX)):
        state = _int_state(summary.get(field, _MISSING), maximum)
        metric_states[output] = state
        metrics[output] = summary[field] if state == "present" else None
        if state in {"missing", "null"}:
            missing_fields.append(f"summary.{field}")
        elif state == "invalid":
            invalid_fields.append(f"summary.{field}")

    usage = raw.get("usage", _MISSING)
    if usage is _MISSING:
        usage_state = "missing"
        rows: list[object] = []
        missing_fields.append("usage")
    elif usage is None:
        usage_state = "null"
        rows = []
        missing_fields.append("usage")
    elif isinstance(usage, list):
        if len(usage) > _MAX_USAGE_ROWS:
            raise VoucherHistoryStatisticsError("usage_limit_exceeded")
        usage_state = "empty" if not usage else "nonempty"
        rows = usage
    else:
        usage_state = "invalid"
        rows = []
        invalid_fields.append("usage")

    coverage = {
        "row_count": len(rows),
        "invalid_row_count": 0,
        "fields": {
            "count": {"present_count": 0, "valid_type_count": 0, "null_count": 0,
                      "missing_count": 0, "invalid_count": 0},
            "timeInterval": {"present_count": 0, "valid_type_count": 0, "null_count": 0,
                              "missing_count": 0, "invalid_count": 0},
            "time": {"present_count": 0, "valid_type_count": 0, "null_count": 0,
                      "missing_count": 0, "invalid_count": 0},
        },
        "unknown_field_count": 0,
    }
    for row in rows:
        if not isinstance(row, Mapping):
            coverage["invalid_row_count"] += 1
            continue
        coverage["unknown_field_count"] += _unknown_count(row, _USAGE_FIELDS)
        for field, maximum, minimum in (
                ("count", _INT32_MAX, 0),
                ("timeInterval", _INT32_MAX, -(2**31)),
                ("time", _INT64_MAX, -(2**63))):
            state = _int_state(row.get(field, _MISSING), maximum, minimum)
            counts = coverage["fields"][field]
            if state != "missing":
                counts["present_count"] += 1
            if state == "present":
                counts["valid_type_count"] += 1
            elif state == "null":
                counts["null_count"] += 1
            elif state == "missing":
                counts["missing_count"] += 1
            else:
                counts["invalid_count"] += 1

    partial = (summary_state != "present" or usage_state in {"missing", "null", "invalid"}
               or bool(invalid_fields) or bool(unknown_fields)
               or any(state in {"missing", "null"} for state in metric_states.values())
               or coverage["invalid_row_count"] > 0
               or coverage["unknown_field_count"] > 0
               or any(v["missing_count"] or v["null_count"] or v["invalid_count"]
                      for v in coverage["fields"].values()))
    return {
        "window_seconds": 86400,
        "summary_state": summary_state,
        "summary_field_states": metric_states,
        **metrics,
        "usage_state": usage_state,
        "usage_coverage": coverage,
        "missing_fields": missing_fields,
        "invalid_fields": invalid_fields,
        "unknown_field_count": unknown_fields,
        "partial": bool(partial),
        "server_completeness": "not_asserted",
    }
