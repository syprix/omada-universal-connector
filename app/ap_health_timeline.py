"""Bounded, redacted projection of documented AP health score history."""
from __future__ import annotations


class ApHealthTimelineError(ValueError):
    """Input or bounds cannot be handled safely."""

    def __init__(self, code: str = "ap_health_timeline_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_FIELDS = 32
_MAX_POINTS = 256
_INT64_MAX = 2**63 - 1
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def project_ap_health_timeline(raw: object, start_ms: int, end_ms: int) -> dict[str, object]:
    """Return only timestamp/score pairs, marking all uncertainty as partial.

    ``null`` score values are omitted and marked partial; they are never
    converted to a numeric score. The caller supplies the fixed query window.
    """
    if (type(start_ms) is not int or type(end_ms) is not int or
            not 0 <= start_ms <= end_ms <= _INT64_MAX):
        raise ApHealthTimelineError()
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise ApHealthTimelineError()

    data: dict[str, object] = {}
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0

    if "scores" not in raw:
        missing.append("scores")
        omitted_count += 1
    elif not isinstance(raw["scores"], list):
        omitted.add("scores")
        omitted_count += 1
    else:
        source = raw["scores"]
        if len(source) > _MAX_POINTS:
            raise ApHealthTimelineError()
        points: list[dict[str, object]] = []
        for index, point in enumerate(source):
            if not isinstance(point, dict) or len(point) > _MAX_FIELDS:
                if isinstance(point, dict):
                    raise ApHealthTimelineError()
                omitted.add("invalid_points")
                omitted_count += 1
                continue

            projected: dict[str, object] = {}
            for field in ("time", "score"):
                path = f"scores[{index}].{field}"
                if field not in point:
                    missing.append(path)
                    omitted_count += 1
                    continue
                value = point[field]
                if field == "time":
                    valid = (type(value) is int and 0 <= value <= _INT64_MAX and
                             start_ms <= value <= end_ms)
                    output_field = "time_ms"
                else:
                    if value is None:
                        omitted.add(path)
                        omitted_count += 1
                        continue
                    valid = (type(value) is int and _INT32_MIN <= value <= _INT32_MAX)
                    output_field = "score"

                if valid:
                    projected[output_field] = value
                else:
                    omitted.add(path)
                    omitted_count += 1

            extras = sum(1 for key in point if key not in {"time", "score"})
            if extras:
                omitted.add("unknown_fields")
                omitted_count += extras
            points.append(projected)
        data["scores"] = points

    extras = sum(1 for key in raw if key != "scores")
    if extras:
        omitted.add("unknown_fields")
        omitted_count += extras

    return {
        "status": "ok",
        "resource": "ap_health_timeline",
        "data": data,
        "partial": bool(missing or omitted_count),
        "missing_fields": missing,
        "omitted_field_count": omitted_count,
        "omitted_fields": sorted(omitted),
    }
