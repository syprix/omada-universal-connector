"""Safe projection of the most recent site WLAN optimization status."""
from __future__ import annotations


class RfPlanningResultError(ValueError):
    """The upstream result does not match its documented shape."""

    def __init__(self, code: str = "rf_planning_result_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_FIELDS = 16
_MAX_KEY_LENGTH = 128


def project_rf_planning_result(raw: object) -> dict[str, object]:
    """Return bounded status and score indices; discard planning IDs."""
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise RfPlanningResultError()
    if any(not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH for key in raw):
        raise RfPlanningResultError()

    fields = (
        ("status", "status", lambda value: type(value) is int and value in (0, 1, 2, 3)),
        ("beforeIndex", "before_index", lambda value: type(value) is int and 0 <= value <= 100),
        ("afterIndex", "after_index", lambda value: type(value) is int and 0 <= value <= 100),
        ("failType", "failure_stage", lambda value: type(value) is int and value in (0, 1)),
    )
    projected: dict[str, object] = {}
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0
    for source, target, valid in fields:
        if source not in raw:
            if source == "status":
                missing.append(source)
                omitted_count += 1
            continue
        if valid(raw[source]):
            projected[target] = raw[source]
        else:
            omitted.add(f"invalid_{target}")
            omitted_count += 1

    known = {"status", "beforeIndex", "afterIndex", "failType", "planningHistroyId"}
    extras = sum(1 for key in raw if key not in known)
    redacted = int("planningHistroyId" in raw)
    if extras:
        omitted.add("unknown_fields")
        omitted_count += extras
    return {
        "status": "ok",
        "resource": "rf_planning_result",
        "data": projected,
        "partial": bool(missing or omitted_count),
        "missing_fields": missing,
        "omitted_field_count": omitted_count,
        "omitted_fields": sorted(omitted),
        "redacted_field_count": redacted,
    }
