"""Bounded projection for the site wireless IPS configuration read."""

from __future__ import annotations

from collections.abc import Mapping


class SiteWipsConfigError(ValueError):
    """The controller response has an invalid outer shape."""


def _int32(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and -(2**31) <= value < 2**31


def project_site_wips_config(result: object) -> dict[str, object]:
    if not isinstance(result, Mapping) or len(result) > 12:
        raise SiteWipsConfigError("result must be a bounded object")

    missing = invalid = 0
    known = {"status", "deauthEn", "dynamicEn", "lockTime"}
    unknown = sum(key not in known for key in result)

    def read_bool(key: str) -> bool | None:
        nonlocal missing, invalid
        if key not in result:
            missing += 1
            return None
        value = result.get(key)
        if not isinstance(value, bool):
            invalid += 1
            return None
        return value

    enabled = read_bool("status")
    deauth_enabled = read_bool("deauthEn")
    dynamic_enabled = read_bool("dynamicEn")

    lock_time: int | None = None
    if "lockTime" in result:
        value = result.get("lockTime")
        if not _int32(value) or not 300 <= value <= 36_000:
            invalid += 1
        else:
            lock_time = value
    elif dynamic_enabled is True:
        missing += 1

    return {
        "data": {
            "enabled": enabled,
            "deauthentication_enabled": deauth_enabled,
            "dynamic_blocking_enabled": dynamic_enabled,
            "lock_time_seconds": lock_time,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid),
    }
