"""Typed, redacted projection for the documented site speed-test setting."""
from __future__ import annotations

from typing import Any


class SpeedTestSettingsError(ValueError):
    """A response does not satisfy the documented speed-test setting schema."""

    def __init__(self, code: str = "speed_test_settings_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_FIELDS = frozenset({
    "autoSpeedTest", "timingType", "hour", "minute", "dayOfWeek",
    "dayOfMonth", "resource", "featureDescription",
})
_INT_RANGES = {
    "timingType": frozenset({1, 2, 3}),
    "hour": range(0, 24),
    "minute": range(0, 60),
    "resource": frozenset({0, 1, 2}),
}


def _int_array(value: Any, *, minimum: int, maximum: int) -> list[int] | None:
    if not isinstance(value, list) or len(value) > maximum - minimum + 1:
        return None
    if any(type(item) is not int or not minimum <= item <= maximum for item in value):
        return None
    return list(value)


def project_speed_test_settings(raw: object) -> dict[str, object]:
    """Project the documented GET result, omitting descriptive free text.

    The API documents ``autoSpeedTest`` as required. Schedule fields are
    conditionally required for weekly and monthly schedules. ``featureDescription``
    and unknown response fields are not returned.
    """
    if not isinstance(raw, dict) or len(raw) > 32:
        raise SpeedTestSettingsError()
    data: dict[str, object] = {}
    missing: list[str] = []
    omitted: set[str] = set()
    unknown_count = 0
    invalid: set[str] = set()
    if "autoSpeedTest" not in raw:
        missing.append("autoSpeedTest")
    elif type(raw["autoSpeedTest"]) is bool:
        data["auto_speed_test"] = raw["autoSpeedTest"]
    else:
        invalid.add("autoSpeedTest")
    for field, allowed in _INT_RANGES.items():
        if field not in raw:
            continue
        value = raw[field]
        if type(value) is not int or value not in allowed:
            invalid.add(field)
            continue
        data[{"timingType": "timing_type", "resource": "resource"}.get(field, field)] = value

    for field, minimum, maximum in (("dayOfWeek", 0, 6), ("dayOfMonth", 1, 31)):
        if field in raw:
            values = _int_array(raw[field], minimum=minimum, maximum=maximum)
            if values is None:
                invalid.add(field)
                continue
            data[{"dayOfWeek": "days_of_week", "dayOfMonth": "days_of_month"}[field]] = values

    if raw.get("timingType") == 2 and "dayOfWeek" not in raw:
        missing.append("dayOfWeek")
    if raw.get("timingType") == 3 and "dayOfMonth" not in raw:
        missing.append("dayOfMonth")

    if "featureDescription" in raw:
        omitted.add("featureDescription")
    unknown_count = sum(1 for field in raw if field not in _FIELDS)
    if unknown_count:
        omitted.add("unknown_fields")
    if invalid:
        omitted.update(invalid)

    return {
        "status": "ok",
        "resource": "speed_test_settings",
        "data": data,
        "partial": bool(missing or omitted),
        "missing_fields": missing,
        "invalid_fields": sorted(invalid),
        "omitted_field_count": (unknown_count + int("featureDescription" in raw)
                                + len(invalid)),
        "omitted_fields": sorted(omitted),
    }
