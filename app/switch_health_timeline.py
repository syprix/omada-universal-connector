"""Bounded projection of the documented switch health score timeline."""
from __future__ import annotations


class SwitchHealthTimelineError(ValueError):
    """Input or bounds cannot be handled safely."""

    def __init__(self, code: str = "switch_health_timeline_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_FIELDS = 32
_MAX_POINTS = 256
_MAX_KEY_LENGTH = 128
_INT64_MAX = 2**63 - 1
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def project_switch_health_timeline(raw: object, start_ms: int,
                                   end_ms: int) -> dict[str, object]:
    """Keep only in-window timestamp/score pairs and report omissions."""
    if (type(start_ms) is not int or type(end_ms) is not int or
            not 0 <= start_ms <= end_ms <= _INT64_MAX):
        raise SwitchHealthTimelineError()
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise SwitchHealthTimelineError()
    if any(not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH for key in raw):
        raise SwitchHealthTimelineError()

    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0
    points: list[dict[str, int]] = []
    source = raw.get("scores")
    if "scores" not in raw:
        missing.append("scores")
        omitted_count += 1
    elif not isinstance(source, list):
        omitted.add("scores")
        omitted_count += 1
    else:
        if len(source) > _MAX_POINTS:
            raise SwitchHealthTimelineError()
        for index, point in enumerate(source):
            if not isinstance(point, dict):
                omitted.add("invalid_points")
                omitted_count += 1
                continue
            if len(point) > _MAX_FIELDS or any(
                    not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH
                    for key in point):
                raise SwitchHealthTimelineError()
            projected: dict[str, int] = {}
            skip = False
            for field in ("time", "score"):
                path = f"scores[{index}].{field}"
                if field not in point:
                    missing.append(path)
                    omitted_count += 1
                    if field == "time":
                        skip = True
                    continue
                value = point[field]
                if field == "time":
                    valid = (type(value) is int and 0 <= value <= _INT64_MAX and
                             start_ms <= value <= end_ms)
                    out_key = "time_ms"
                    skip = skip or not valid
                else:
                    valid = type(value) is int and _INT32_MIN <= value <= _INT32_MAX
                    out_key = "score"
                if valid:
                    projected[out_key] = value
                else:
                    omitted.add(path)
                    omitted_count += 1
            extras = sum(key not in {"time", "score"} for key in point)
            if extras:
                omitted.add("unknown_fields")
                omitted_count += extras
            if not skip:
                points.append(projected)
    extras = sum(key != "scores" for key in raw)
    if extras:
        omitted.add("unknown_fields")
        omitted_count += extras
    return {"status": "ok", "resource": "switch_health_timeline",
            "data": {"scores": points}, "partial": bool(missing or omitted_count),
            "missing_fields": missing, "omitted_field_count": omitted_count,
            "omitted_fields": sorted(omitted)}
