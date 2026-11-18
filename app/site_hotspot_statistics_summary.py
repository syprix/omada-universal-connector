"""Compact identity-free aggregates for hotspot authentication statistics."""
from __future__ import annotations

from typing import Any


class SiteHotspotStatisticsSummaryError(ValueError):
    """Raised when the hotspot statistics response is malformed or oversized."""


_AUTH_TYPES = ("noAuth", "simplePassword", "hotspot", "facebook", "externalRadius",
               "externalPortal", "ldap", "google")
_HOTSPOT_TYPES = ("total", "voucher", "localUser", "sms", "form", "hotspotRadius")
_FIELDS = {"lastConnection", "authTypeDistribution", "hotspotDistribution"}
_SAMPLE_FIELDS = {"newNum", "existingNum", "startTime", "endTime"}
_MAX_SAMPLES = 2_000
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1


def _project_distribution(value: Any, fields: tuple[str, ...]) -> tuple[dict[str, int | None], int, int, int]:
    if value is None:
        return {key: None for key in fields}, len(fields), 0, 0
    if not isinstance(value, dict) or len(value) > len(fields) + 2:
        raise SiteHotspotStatisticsSummaryError("response_invalid")
    counts: dict[str, int | None] = {}
    missing = invalid = 0
    unknown = len(set(value) - set(fields))
    for key in fields:
        if key not in value:
            counts[key] = None
            missing += 1
            continue
        number = value[key]
        if type(number) is not int or not 0 <= number <= _INT32_MAX:
            counts[key] = None
            invalid += 1
        else:
            counts[key] = number
    return counts, missing, invalid, unknown


def project_site_hotspot_statistics_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 6:
        raise SiteHotspotStatisticsSummaryError("response_invalid")
    missing = invalid = 0
    unknown = len(set(result) - _FIELDS)
    samples = result.get("lastConnection", [])
    if "lastConnection" not in result:
        missing += 1
    if samples is None:
        missing += 1
        samples = []
    if not isinstance(samples, list) or len(samples) > _MAX_SAMPLES:
        raise SiteHotspotStatisticsSummaryError("response_invalid")

    new_values: list[int] = []
    existing_values: list[int] = []
    times: list[int] = []
    sample_complete = {"newNum": True, "existingNum": True}
    for row in samples:
        if not isinstance(row, dict) or len(row) > 6:
            invalid += 1
            sample_complete["newNum"] = sample_complete["existingNum"] = False
            continue
        unknown += len(set(row) - _SAMPLE_FIELDS)
        for key, output in (("newNum", new_values), ("existingNum", existing_values)):
            if key not in row:
                missing += 1
                sample_complete[key] = False
                continue
            value = row[key]
            if type(value) is not int or not 0 <= value <= _INT32_MAX:
                invalid += 1
                sample_complete[key] = False
            else:
                output.append(value)
        for key in ("startTime", "endTime"):
            if key not in row:
                missing += 1
                continue
            value = row[key]
            if type(value) is not int or not 0 <= value <= _INT64_MAX:
                invalid += 1
            else:
                times.append(value)

    auth, auth_missing, auth_invalid, auth_unknown = _project_distribution(
        result.get("authTypeDistribution"), _AUTH_TYPES)
    hotspot, type_missing, type_invalid, type_unknown = _project_distribution(
        result.get("hotspotDistribution"), _HOTSPOT_TYPES)
    missing += auth_missing + type_missing
    invalid += auth_invalid + type_invalid
    unknown += auth_unknown + type_unknown
    data: dict[str, object] = {
        "last_connection_sample_count": len(samples),
        "total_new_authenticated_clients": (
            sum(new_values) if sample_complete["newNum"] and len(new_values) == len(samples) else None),
        "total_existing_authenticated_clients": (
            sum(existing_values) if sample_complete["existingNum"] and
            len(existing_values) == len(samples) else None),
        "authentication_type_counts": auth,
        "hotspot_type_counts": hotspot,
    }
    if times:
        data["earliest_source_time"] = min(times)
        data["latest_source_time"] = max(times)
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
