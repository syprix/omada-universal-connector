"""Redacted projection for the documented site MAC-filter setting."""
from __future__ import annotations

from typing import Any


MAX_SOURCE_FIELDS = 16
MAX_DIRECTION_FIELDS = 16
MAX_SELECTOR_IDS = 256
FILTER_MODES = {0: "allow", 1: "deny"}


class SiteMacFilteringError(ValueError):
    """Raised when the fixed MAC-filter response exceeds safe bounds."""


def _selector_count(value: Any) -> int | None:
    if not isinstance(value, list):
        return None
    if len(value) > MAX_SELECTOR_IDS:
        raise SiteMacFilteringError("response_invalid")
    if any(not isinstance(item, str) for item in value):
        return None
    return len(value)


def project_site_mac_filtering_general_state(result: Any) -> dict[str, object]:
    """Expose only documented booleans, mode and counts of selector IDs."""
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise SiteMacFilteringError("response_invalid")

    data: dict[str, object] = {"direction_present": "direction" in result}
    missing = int("enable" not in result)
    invalid = 0
    unknown = len(set(result) - {"enable", "filterMode", "direction"})

    if "enable" in result:
        enabled = result["enable"]
        if type(enabled) is bool:
            data["enabled"] = enabled
        else:
            invalid += 1

    if "filterMode" in result:
        mode = result["filterMode"]
        if type(mode) is int and mode in FILTER_MODES:
            data["filter_mode"] = FILTER_MODES[mode]
        else:
            invalid += 1

    direction_invalid = 0
    direction_unknown = 0
    if "direction" in result:
        direction = result["direction"]
        if not isinstance(direction, dict) or len(direction) > MAX_DIRECTION_FIELDS:
            invalid += 1
            direction_invalid += 1
        else:
            projected: dict[str, object] = {}
            allowed = {"lanToWan", "lanToLan", "wanInIds", "vpnInIds"}
            direction_unknown = len(set(direction) - allowed)
            for source, target in (("lanToWan", "lan_to_wan"),
                                   ("lanToLan", "lan_to_lan")):
                if source not in direction:
                    continue
                value = direction[source]
                if type(value) is bool:
                    projected[target] = value
                else:
                    invalid += 1
                    direction_invalid += 1
            for source, target in (("wanInIds", "wan_selector_count"),
                                   ("vpnInIds", "vpn_selector_count")):
                if source not in direction:
                    continue
                count = _selector_count(direction[source])
                if count is None:
                    invalid += 1
                    direction_invalid += 1
                else:
                    projected[target] = count
            data["direction"] = projected
            unknown += direction_unknown

    return {
        "data": data,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "direction_invalid_field_count": direction_invalid,
        "direction_unknown_field_count": direction_unknown,
        "partial": bool(missing or invalid or unknown),
    }
