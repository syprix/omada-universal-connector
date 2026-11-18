"""Redacted read-only projections for documented channel-limit settings."""
from __future__ import annotations


class ChannelLimitError(ValueError):
    """An input exceeds safe projection bounds or is not an object."""

    def __init__(self, code: str = "channel_limit_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_FIELDS = 32
_SITE_FIELDS = frozenset({"channelLimit"})
_AP_BOOL_FIELDS = frozenset({"supportChannelLimit", "defaultInstType5g", "defaultInstType6g"})
_AP_INT_FIELDS = frozenset({"channelLimitType"})
_AP_FIELDS = _AP_BOOL_FIELDS | _AP_INT_FIELDS


def _input(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or len(value) > _MAX_FIELDS:
        raise ChannelLimitError()
    return value


def project_site_channel_limit(raw: object) -> dict[str, object]:
    """Project only the deprecated site-level ``channelLimit.enable`` flag."""
    value = _input(raw)
    data: dict[str, bool] = {}
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0

    if "channelLimit" not in value:
        missing.append("channelLimit.enable")
        omitted_count += 1
    elif not isinstance(value["channelLimit"], dict):
        omitted.add("channelLimit")
        omitted_count += 1
    else:
        nested = value["channelLimit"]
        if len(nested) > _MAX_FIELDS:
            raise ChannelLimitError()
        if "enable" not in nested:
            missing.append("channelLimit.enable")
            omitted_count += 1
        elif type(nested["enable"]) is bool:
            data["enable"] = nested["enable"]
        else:
            omitted.add("channelLimit.enable")
            omitted_count += 1
        extra_count = sum(1 for key in nested if key != "enable")
        if extra_count:
            omitted.add("unknown_fields")
            omitted_count += extra_count

    extra_top_count = sum(1 for key in value if key not in _SITE_FIELDS)
    if extra_top_count:
        omitted.add("unknown_fields")
        omitted_count += extra_top_count

    return {
        "status": "ok", "resource": "site_channel_limit", "data": data,
        "partial": bool(missing or omitted_count),
        "missing_fields": missing,
        "omitted_field_count": omitted_count,
        "omitted_fields": sorted(omitted),
    }


def project_ap_channel_limit(raw: object) -> dict[str, object]:
    """Project documented AP channel-limit values without interpreting enums."""
    value = _input(raw)
    data: dict[str, bool | int] = {}
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0

    for field in sorted(_AP_FIELDS):
        if field not in value:
            missing.append(field)
            omitted_count += 1
            continue
        item = value[field]
        if field in _AP_BOOL_FIELDS:
            valid = type(item) is bool
        else:
            valid = type(item) is int and item in (0, 1, 2)
        if valid:
            data[field] = item
        else:
            omitted.add(field)
            omitted_count += 1

    extra_count = sum(1 for field in value if field not in _AP_FIELDS)
    if extra_count:
        omitted.add("unknown_fields")
        omitted_count += extra_count

    return {
        "status": "ok", "resource": "ap_channel_limit", "data": data,
        "partial": bool(missing or omitted_count),
        "missing_fields": sorted(missing),
        "omitted_field_count": omitted_count,
        "omitted_fields": sorted(omitted),
    }
