"""Redacted summary of a site's documented automatic recovery settings."""
from __future__ import annotations

from collections.abc import Mapping


class IntelliRecoverSummaryError(ValueError):
    pass


_FIELDS = frozenset(("id", "autoFlag", "firstRebootPoeInterval", "limitNum",
                     "rebootPoeInterval"))


def _int32(value: object) -> bool:
    return type(value) is int and 0 <= value <= 2_147_483_647


def summarize_intelli_recover_settings(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 16:
        raise IntelliRecoverSummaryError("result_invalid")
    unknown = sum(key not in _FIELDS for key in value)

    auto = value.get("autoFlag")
    if auto is not None and type(auto) is not bool:
        raise IntelliRecoverSummaryError("auto_flag_invalid")
    limit = value.get("limitNum")
    if limit is not None and not _int32(limit):
        raise IntelliRecoverSummaryError("limit_invalid")

    interval_reported: dict[str, bool] = {}
    for source, output in (("firstRebootPoeInterval", "initial_interval_reported"),
                           ("rebootPoeInterval", "retry_interval_reported")):
        raw = value.get(source)
        if raw is not None and not _int32(raw):
            raise IntelliRecoverSummaryError("interval_invalid")
        interval_reported[output] = raw is not None

    return {
        "automatic_recovery_enabled": auto,
        "reboot_device_limit": limit,
        **interval_reported,
        "interval_values_returned": False,
        "interval_units_documented": False,
        "unknown_field_count": unknown,
        "partial": bool(auto is None or limit is None or unknown or
                         not all(interval_reported.values())),
        "setting_id_returned": False,
    }
