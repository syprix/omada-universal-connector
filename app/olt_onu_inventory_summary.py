"""Aggregate ONU inventory and reboot-status reads without exposing identities."""
from __future__ import annotations

from typing import Any
import re


MAX_ROWS = 1000
MAX_FIELDS = 32
_ONU_FIELDS = {
    "key", "ponPortId", "ponPortStr", "onuId", "onuDescription", "serialNumber",
    "macAddress", "lineProfile", "serviceProfile", "servicePortProfile",
    "adminStatus", "onlineStatus", "configStatus", "matchStatus", "activeStatus",
    "equipmentId", "softwareVersion", "hardwareVersion", "receivedOpticalPower",
    "transmittedOpticalPower", "softWareVersion",
}
_REBOOT_FIELDS = {"key", "onlineStatus"}
_ONLINE_STATES = {"ONLINE", "OFFLINE", "SUCCESSFUL", "UPGRADING", "FAILED", "WAITING_UPGRADE"}
_ADMIN_STATES = {"ACTIVATE", "DEACTIVATE", "ACTIVATED", "DEACTIVATED"}
_CONFIG_STATES = {"SUCCESS", "FAILED"}
_MATCH_STATES = {"MATCH", "MISMATCH"}
_ACTIVE_STATES = {"ACTIVE", "INACTIVE"}
_IDENTITY_FIELDS = {
    "key", "ponPortId", "ponPortStr", "onuId", "onuDescription", "serialNumber",
    "macAddress", "lineProfile", "serviceProfile", "servicePortProfile", "equipmentId",
    "softwareVersion", "hardwareVersion", "receivedOpticalPower",
    "transmittedOpticalPower", "softWareVersion",
}


class OltOnuInventoryError(ValueError):
    """Raised when an ONU inventory response exceeds supported bounds."""


_PON_SELECTOR_ITEM = re.compile(
    r"GPON ([1-9][0-9]{0,2})/([1-9][0-9]{0,2})/([1-9][0-9]{0,2})(?:-([1-9][0-9]{0,2}))?\Z"
)


def validate_pon_port_selector(value: Any) -> str:
    """Validate the documented PON selector syntax without accepting URL/path fragments."""
    if not isinstance(value, str) or not value or len(value) > 512:
        raise OltOnuInventoryError("pon_port_invalid")
    items = value.split(",")
    if len(items) > 64:
        raise OltOnuInventoryError("pon_port_invalid")
    for item in items:
        match = _PON_SELECTOR_ITEM.fullmatch(item)
        if not match:
            raise OltOnuInventoryError("pon_port_invalid")
        numbers = [int(part) for part in match.groups() if part is not None]
        if any(number > 128 for number in numbers):
            raise OltOnuInventoryError("pon_port_invalid")
        if len(numbers) == 4 and (numbers[3] < numbers[2] or numbers[3] - numbers[2] > 127):
            raise OltOnuInventoryError("pon_port_invalid")
    return value


def _increment(counts: dict[str, int], value: str) -> None:
    counts[value] = counts.get(value, 0) + 1


def _project_status_rows(result: Any, *, reboot_only: bool) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > MAX_ROWS:
        raise OltOnuInventoryError("response_invalid")
    allowed = _REBOOT_FIELDS if reboot_only else _ONU_FIELDS
    missing = 0
    invalid = 0
    unknown = 0
    redacted = 0
    online: dict[str, int] = {}
    admin: dict[str, int] = {}
    config: dict[str, int] = {}
    match: dict[str, int] = {}
    active: dict[str, int] = {}
    optical_presence = {"received": 0, "transmitted": 0}
    for row in result:
        if not isinstance(row, dict) or len(row) > MAX_FIELDS:
            invalid += 1
            continue
        unknown += len(set(row) - allowed)
        redacted += len(row)
        identity = row.get("key")
        if identity is not None and (not isinstance(identity, str) or len(identity) > 256):
            invalid += 1
        for field, counts, states in (
            ("onlineStatus", online, _ONLINE_STATES),
            ("adminStatus", admin, _ADMIN_STATES),
            ("configStatus", config, _CONFIG_STATES),
            ("matchStatus", match, _MATCH_STATES),
            ("activeStatus", active, _ACTIVE_STATES),
        ):
            if field not in allowed:
                continue
            value = row.get(field)
            if value is None:
                missing += 1
            elif isinstance(value, str) and len(value) <= 32 and value in states:
                _increment(counts, value)
            else:
                invalid += 1
        if not reboot_only:
            for field, key in (("receivedOpticalPower", "received"),
                               ("transmittedOpticalPower", "transmitted")):
                value = row.get(field)
                if value is not None:
                    if isinstance(value, str) and len(value) <= 32:
                        optical_presence[key] += 1
                    else:
                        invalid += 1
    data: dict[str, object] = {"onu_count": len(result), "online_status_counts": online}
    if not reboot_only:
        data.update({
            "admin_status_counts": admin,
            "configuration_status_counts": config,
            "profile_match_status_counts": match,
            "active_status_counts": active,
            "optical_power_reported_counts": optical_presence,
        })
    return {"data": data, "partial": bool(missing or invalid or unknown),
            "missing_count": missing, "invalid_count": invalid,
            "unknown_field_count": unknown, "redacted_field_count": redacted}


def project_olt_onu_inventory_summary(result: Any) -> dict[str, object]:
    return _project_status_rows(result, reboot_only=False)


def project_olt_onu_reboot_status_summary(result: Any) -> dict[str, object]:
    return _project_status_rows(result, reboot_only=True)
