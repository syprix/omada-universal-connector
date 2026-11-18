"""Safe projection for the deprecated site WLAN-group detail read."""
from __future__ import annotations

from collections.abc import Mapping


class SiteWlanGroupDetailError(ValueError):
    """The documented WLAN-group detail response is malformed."""


_IDENTIFIER_FIELDS = frozenset(("wlanId", "id", "cloneWlanId", "site"))
_FIELDS = _IDENTIFIER_FIELDS | frozenset(("name", "primary", "clone", "resource"))


def project_site_wlan_group_detail(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 16:
        raise SiteWlanGroupDetailError("WLAN-group detail must be a bounded object")
    data: dict[str, object] = {}
    invalid = 0
    for key in _IDENTIFIER_FIELDS:
        if key in value and not isinstance(value[key], str):
            invalid += 1
    if "name" in value:
        name = value["name"]
        if (not isinstance(name, str) or not 1 <= len(name) <= 128 or
                any(ord(char) < 0x20 or ord(char) == 0x7f for char in name)):
            invalid += 1
        else:
            data["name"] = name
    for key in ("primary", "clone"):
        if key not in value:
            continue
        if type(value[key]) is bool:
            data[key] = value[key]
        else:
            invalid += 1
    if "resource" in value:
        resource = value["resource"]
        if type(resource) is int and resource in (0, 1, 2):
            data["resource"] = resource
        else:
            invalid += 1
    unknown = sum(key not in _FIELDS for key in value)
    return {
        "data": data,
        "missing_field_count": 0,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(invalid or unknown),
    }
