"""Bounded projection for the site WLAN and MAC-authentication SSID listing."""
from __future__ import annotations

from collections.abc import Mapping


class MacAuthSsidInventoryError(ValueError):
    """The documented WLAN/SSID list response is malformed."""


_WLAN_FIELDS = frozenset(("wlanId", "wlanName", "ssidList"))
_SSID_FIELDS = frozenset(("id", "ssidId", "ssidName"))
MAX_WLANS = 100
MAX_SSIDS = 500
MAX_NAME_LENGTH = 128


def _valid_name(value: object) -> bool:
    return (isinstance(value, str) and 1 <= len(value) <= MAX_NAME_LENGTH and
            value == value.strip() and
            not any(ord(char) < 0x20 or ord(char) == 0x7f for char in value))


def summarize_mac_auth_ssid_inventory(value: object, *, device_type: int
                                      ) -> dict[str, object]:
    if (not isinstance(value, list) or type(device_type) is not int or
            device_type not in (1, 2, 3)):
        raise MacAuthSsidInventoryError("invalid WLAN SSID response")
    ssid_total_count = sum(
        len(wlan["ssidList"]) for wlan in value
        if isinstance(wlan, Mapping) and isinstance(wlan.get("ssidList"), list))
    items: list[dict[str, object]] = []
    returned_ssids = invalid = unknown = missing = 0
    for wlan in value[:MAX_WLANS]:
        if not isinstance(wlan, Mapping) or len(wlan) > 16:
            invalid += 1
            continue
        unknown += sum(key not in _WLAN_FIELDS for key in wlan)
        name = wlan.get("wlanName")
        ssid_rows = wlan.get("ssidList")
        if not _valid_name(name):
            invalid += 1
            continue
        if not isinstance(ssid_rows, list):
            missing += 1
            ssid_rows = []
        ssids: list[str] = []
        for row in ssid_rows:
            if returned_ssids >= MAX_SSIDS:
                break
            if not isinstance(row, Mapping) or len(row) > 8:
                invalid += 1
                continue
            unknown += sum(key not in _SSID_FIELDS for key in row)
            ssid_name = row.get("ssidName")
            if not _valid_name(ssid_name):
                invalid += 1
                continue
            ssids.append(ssid_name)
            returned_ssids += 1
        items.append({"wlan_name": name, "ssid_names": ssids})
    truncated = len(value) > MAX_WLANS or ssid_total_count > returned_ssids
    return {
        "status": "ok",
        "resource": "site_mac_auth_ssid_inventory",
        "device_type": device_type,
        "wlan_count": len(value),
        "returned_wlan_count": len(items),
        "ssid_count": ssid_total_count,
        "returned_ssid_count": returned_ssids,
        "items": items,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or truncated),
    }
