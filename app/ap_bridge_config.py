"""Redacted summary of the documented AP P2P bridge configuration."""
from __future__ import annotations


class ApBridgeConfigError(ValueError):
    """The bridge configuration is outside projection bounds."""


_ROOT = frozenset({"bridgeSsidName", "bridgeSsidPassword", "hwSwitch",
                   "paringCode", "tdmaConfig"})
_TDMA = frozenset({"status", "clients", "notSupportTdmaClients"})
_CLIENT_FIELDS = frozenset({"mac", "priority", "name", "model", "modelVersion"})
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_MAX_CLIENTS = 256


def _code(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def summarize_ap_bridge_config(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 16 or any(
            not isinstance(key, str) or len(key) > 128 for key in raw):
        raise ApBridgeConfigError()
    unknown = sum(1 for key in raw if key not in _ROOT)
    redacted = sum(1 for key in ("bridgeSsidName", "bridgeSsidPassword", "paringCode")
                   if key in raw)
    invalid = 0
    missing = 0
    hw_switch = raw.get("hwSwitch")
    if "hwSwitch" in raw and (not _code(hw_switch) or hw_switch not in (0, 1)):
        hw_switch = None
        invalid += 1
    elif "hwSwitch" not in raw:
        missing += 1
    tdma_status = None
    priority_counts: dict[int, int] | None = None
    client_count: int | None = None
    unsupported_count: int | None = None
    tdma = raw.get("tdmaConfig")
    if "tdmaConfig" in raw:
        if not isinstance(tdma, dict) or len(tdma) > 16 or any(
                not isinstance(key, str) or len(key) > 128 for key in tdma):
            raise ApBridgeConfigError()
        unknown += sum(1 for key in tdma if key not in _TDMA)
        status = tdma.get("status")
        if "status" in tdma:
            if _code(status) and status in (0, 1):
                tdma_status = status
            else:
                invalid += 1
        else:
            missing += 1
        if "clients" in tdma:
            priority_counts = {0: 0, 1: 0, 2: 0}
        for field, target in (("clients", "supported"),
                              ("notSupportTdmaClients", "unsupported")):
            if field not in tdma:
                missing += 1
                continue
            rows = tdma[field]
            if not isinstance(rows, list) or len(rows) > _MAX_CLIENTS:
                raise ApBridgeConfigError()
            if target == "supported":
                client_count = len(rows)
            else:
                unsupported_count = len(rows)
            for row in rows:
                if not isinstance(row, dict) or len(row) > 16:
                    invalid += 1
                    continue
                unknown += sum(1 for key in row if key not in _CLIENT_FIELDS)
                redacted += sum(1 for key in ("mac", "name", "model", "modelVersion")
                                if key in row)
                if "priority" in row:
                    priority = row["priority"]
                    if type(priority) is int and priority in priority_counts:
                        priority_counts[priority] += 1
                    else:
                        invalid += 1
                elif target == "supported":
                    missing += 1
    else:
        missing += 1
    partial = bool(missing or unknown or invalid)
    return {
        "status": "ok", "resource": "ap_bridge_config",
        "data": {"hw_switch_code": hw_switch,
                 "tdma_status_code": tdma_status,
                 "tdma_client_count": client_count,
                 "tdma_unsupported_client_count": unsupported_count,
                 "client_priority_counts": (dict(sorted(priority_counts.items()))
                                            if priority_counts is not None else None)},
        "redacted_field_count": redacted,
        "missing_field_count": missing,
        "unknown_field_count": unknown,
        "invalid_field_count": invalid,
        "partial": partial,
    }
