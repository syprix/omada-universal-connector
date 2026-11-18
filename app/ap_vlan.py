"""Redacted projection of documented AP VLAN V2 settings."""
from __future__ import annotations


class ApVlanError(ValueError):
    """The AP VLAN result cannot be bounded or projected safely."""

    def __init__(self, code: str = "ap_vlan_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_ROOT_FIELDS = frozenset({"mvlanSetting", "voipVlanSetting"})
_MVLAN_FIELDS = frozenset({"mode", "bridgeVlan", "lanNetworkId"})
_VOIP_FIELDS = frozenset({"mode", "voipBridgeVlan", "ipType", "lanNetworkId", "ip", "ipMask", "ipGateway", "ipDns1", "ipDns2"})
_REDACTED_FIELDS = frozenset({"lanNetworkId", "ip", "ipMask", "ipGateway", "ipDns1", "ipDns2"})
_MAX_ROOT_FIELDS = 8
_MAX_NESTED_FIELDS = 16
_MAX_KEY_LENGTH = 128
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def _int32(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def _project_setting(raw: object, name: str, allowed: frozenset[str],
                     optional_ints: dict[str, tuple[int, int] | None]) -> tuple[dict[str, int], list[str], list[str], int, int]:
    if not isinstance(raw, dict):
        if isinstance(raw, (list, tuple)) and len(raw) > _MAX_NESTED_FIELDS:
            raise ApVlanError()
        return {}, [], [name], 0, 0
    if len(raw) > _MAX_NESTED_FIELDS:
        raise ApVlanError()
    data: dict[str, int] = {}
    missing: list[str] = []
    invalid: list[str] = []
    unknown = 0
    redacted = 0
    for field, value in raw.items():
        if not isinstance(field, str) or len(field) > _MAX_KEY_LENGTH:
            raise ApVlanError()
        if field not in allowed:
            unknown += 1
            continue
        if field in _REDACTED_FIELDS:
            redacted += 1
            continue
        if field == "mode" or field in optional_ints:
            bounds = optional_ints.get(field, (0, 1))
            if _int32(value) and (bounds is None or bounds[0] <= value <= bounds[1]):
                data[field] = value
            else:
                invalid.append(f"{name}.{field}")
    if "mode" not in raw:
        missing.append(f"{name}.mode")
    return data, missing, invalid, unknown, redacted


def project_ap_vlan(raw: object) -> dict[str, object]:
    """Project only documented VLAN settings; redact network identifiers/addresses.

    The root settings objects are optional. Each present object requires a
    documented ``mode`` value. No VLAN ranges, units, or runtime effects are
    inferred beyond the schema's explicit int32 and enum constraints.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_ROOT_FIELDS:
        raise ApVlanError()
    data: dict[str, dict[str, int]] = {}
    missing: list[str] = []
    invalid: list[str] = []
    unknown = 0
    redacted = 0
    for key, value in raw.items():
        if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
            raise ApVlanError()
        if key not in _ROOT_FIELDS:
            unknown += 1
            continue
        if key == "mvlanSetting":
            projected, miss, bad, unk, redact = _project_setting(
                value, key, _MVLAN_FIELDS, {"bridgeVlan": None})
        else:
            projected, miss, bad, unk, redact = _project_setting(
                value, key, _VOIP_FIELDS, {"voipBridgeVlan": None, "ipType": (0, 1)})
        data[key] = projected
        missing.extend(miss)
        invalid.extend(bad)
        unknown += unk
        redacted += redact
    return {
        "status": "ok",
        "resource": "ap_vlan",
        "data": data,
        "partial": bool(missing or invalid or unknown),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unknown_field_count": unknown,
        "redacted_field_count": redacted,
    }
