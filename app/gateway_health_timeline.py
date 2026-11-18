"""Bounded, redacted projection of documented gateway health score history."""
from __future__ import annotations


class GatewayHealthTimelineError(ValueError):
    """Input or bounds cannot be handled safely."""

    def __init__(self, code: str = "gateway_health_timeline_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_FIELDS = 32
_MAX_POINTS = 256
_MAX_KEY_LENGTH = 128
_INT64_MAX = 2**63 - 1
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def project_gateway_health_timeline(raw: object, start_ms: int,
                                    end_ms: int) -> dict[str, object]:
    """Return only in-window timestamp/score pairs, with no score scale claim.

    The caller supplies the fixed query interval in milliseconds. Null or
    invalid values are omitted and mark the result partial; unknown source
    fields are counted but never copied into the public result.
    """
    if (type(start_ms) is not int or type(end_ms) is not int or
            not 0 <= start_ms <= end_ms <= _INT64_MAX):
        raise GatewayHealthTimelineError()
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise GatewayHealthTimelineError()

    for key in raw:
        if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
            raise GatewayHealthTimelineError()

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
            raise GatewayHealthTimelineError()
        points: list[dict[str, int]] = []
        for index, point in enumerate(source):
            if not isinstance(point, dict):
                omitted.add("invalid_points")
                omitted_count += 1
                continue
            if len(point) > _MAX_FIELDS:
                raise GatewayHealthTimelineError()
            for key in point:
                if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
                    raise GatewayHealthTimelineError()

            projected: dict[str, int] = {}
            omit_point = False
            for field in ("time", "score"):
                path = f"scores[{index}].{field}"
                if field not in point:
                    missing.append(path)
                    omitted_count += 1
                    if field == "time":
                        omit_point = True
                    continue
                value = point[field]
                if field == "time":
                    valid = (type(value) is int and 0 <= value <= _INT64_MAX and
                             start_ms <= value <= end_ms)
                    output_field = "time_ms"
                    if not valid:
                        omit_point = True
                else:
                    if value is None:
                        omitted.add(path)
                        omitted_count += 1
                        continue
                    valid = type(value) is int and _INT32_MIN <= value <= _INT32_MAX
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
            if not omit_point:
                points.append(projected)
        data["scores"] = points

    extras = sum(1 for key in raw if key != "scores")
    if extras:
        omitted.add("unknown_fields")
        omitted_count += extras

    return {
        "status": "ok",
        "resource": "gateway_health_timeline",
        "data": data,
        "partial": bool(missing or omitted_count),
        "missing_fields": missing,
        "omitted_field_count": omitted_count,
        "omitted_fields": sorted(omitted),
    }
