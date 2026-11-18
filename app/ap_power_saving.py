"""Redacted projection of documented AP power-saving GET settings."""
from __future__ import annotations


class ApPowerSavingError(ValueError):
    """The AP power-saving result cannot be bounded or projected safely."""

    def __init__(self, code: str = "ap_power_saving_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_FIELDS = (
    "mode", "timeEnable", "bandEnable", "supportPowerSaving",
    "startTimeH", "endTimeH", "startTimeM", "endTimeM", "bands", "idleDuration",
)
_BOOL_FIELDS = frozenset({"timeEnable", "bandEnable", "supportPowerSaving"})
_TIME_RANGES = {"startTimeH": (0, 23), "endTimeH": (0, 23),
                "startTimeM": (0, 59), "endTimeM": (0, 59)}
_MAX_FIELDS = 16
_MAX_KEY_LENGTH = 128
_MAX_BANDS = 16
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def _int32(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def project_ap_power_saving(raw: object) -> dict[str, object]:
    """Project only documented fields and preserve their values as reported.

    Documented hour/minute and mode bounds are validated. ``idleDuration`` is
    checked only as int32 because the GET schema supplies no further bounds.
    Duplicate band IDs remain in the output list and mark the result partial.
    No behavior, cause, unit, or side-effect interpretation is inferred.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise ApPowerSavingError()

    data: dict[str, bool | int | list[int]] = {}
    missing: list[str] = []
    invalid: list[str] = []
    unknown_field_count = 0
    duplicate_band_count = 0

    for field in _FIELDS:
        if field not in raw:
            missing.append(field)
            continue
        value = raw[field]
        if field in _BOOL_FIELDS:
            if type(value) is bool:
                data[field] = value
            else:
                invalid.append(field)
        elif field == "bands":
            if not isinstance(value, list):
                invalid.append(field)
                continue
            if len(value) > _MAX_BANDS:
                raise ApPowerSavingError()
            bands: list[int] = []
            seen: set[int] = set()
            for band in value:
                if not _int32(band) or band not in (0, 1, 2, 3):
                    invalid.append("bands[]")
                    continue
                if band in seen:
                    duplicate_band_count += 1
                else:
                    seen.add(band)
                bands.append(band)
            data[field] = bands
        elif field == "mode":
            if _int32(value) and value in (0, 1, 2, 3):
                data[field] = value
            else:
                invalid.append(field)
        elif field in _TIME_RANGES:
            low, high = _TIME_RANGES[field]
            if _int32(value) and low <= value <= high:
                data[field] = value
            else:
                invalid.append(field)
        elif _int32(value):
            # idleDuration has no documented GET range beyond int32.
            data[field] = value
        else:
            invalid.append(field)

    for key in raw:
        if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
            raise ApPowerSavingError()
        if key not in _FIELDS:
            unknown_field_count += 1

    return {
        "status": "ok",
        "resource": "ap_power_saving",
        "data": data,
        "partial": bool(missing or invalid or unknown_field_count or duplicate_band_count),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unknown_field_count": unknown_field_count,
        "duplicate_band_count": duplicate_band_count,
    }
