"""Redacted summary of AP point-to-point bridge group membership."""
from __future__ import annotations


class ApP2pInfoError(ValueError):
    """The P2P group response exceeds the projection bounds."""


_ROOT = frozenset({"mainAp", "childAps"})
_DEVICE = frozenset({"deviceMac", "deviceName"})
_MAX_CHILDREN = 1024


def _project_device(value: object) -> tuple[bool, int, int, int]:
    if not isinstance(value, dict) or len(value) > 8:
        return False, 0, 1, 0
    unknown = sum(1 for key in value if key not in _DEVICE)
    invalid = redacted = 0
    for key in _DEVICE:
        if key in value:
            redacted += 1
            if not isinstance(value[key], str) or len(value[key]) > 128:
                invalid += 1
    return True, redacted, invalid, unknown


def summarize_ap_p2p_info(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 8:
        raise ApP2pInfoError()
    unknown = sum(1 for key in raw if key not in _ROOT)
    invalid = missing = redacted = 0
    main_present: bool | None = None
    if "mainAp" not in raw:
        missing += 1
    elif raw["mainAp"] is None:
        main_present = False
    else:
        main_present, count, bad, extra = _project_device(raw["mainAp"])
        redacted += count
        invalid += bad
        unknown += extra

    child_count: int | None = None
    if "childAps" not in raw:
        missing += 1
    elif not isinstance(raw["childAps"], list) or len(raw["childAps"]) > _MAX_CHILDREN:
        invalid += 1
    else:
        child_count = len(raw["childAps"])
        for device in raw["childAps"]:
            valid, count, bad, extra = _project_device(device)
            redacted += count
            invalid += bad
            unknown += extra

    return {
        "status": "ok", "resource": "ap_p2p_info",
        "main_ap_present": main_present, "child_ap_count": child_count,
        "redacted_identity_field_count": redacted,
        "redacted_field_count": redacted, "unknown_field_count": unknown,
        "invalid_field_count": invalid, "missing_field_count": missing,
        "partial": bool(missing or invalid or unknown),
    }
