"""Safe status summary for a device's management WLAN configuration."""
from __future__ import annotations


class ApManagementSsidError(ValueError):
    """The documented management-SSID response cannot be safely summarized."""


_ROOT = frozenset({"status", "name", "security", "broadcast", "pskSetting",
                    "entSetting", "vlanSetting"})
_PSK = frozenset({"securityKey", "versionPsk", "encryptionPsk"})
_ENT = frozenset({"radiusProfileId", "versionEnt", "encryptionEnt"})
_VLAN = frozenset({"mode", "customConfig"})
_VLAN_CUSTOM = frozenset({"customMode", "lanNetworkId", "bridgeVlan", "vlanId"})


def _int(value: object, choices: range | tuple[int, ...]) -> bool:
    return type(value) is int and value in choices


def _string(value: object) -> bool:
    return isinstance(value, str) and len(value) <= 256


def summarize_ap_management_ssid(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 16:
        raise ApManagementSsidError()
    unknown = sum(1 for key in raw if key not in _ROOT)
    invalid = missing = redacted = 0

    enabled = raw.get("status")
    if "status" not in raw:
        missing += 1
        enabled = None
    elif type(enabled) is not bool:
        invalid += 1
        enabled = None

    broadcast = raw.get("broadcast")
    if "broadcast" not in raw:
        missing += 1
        broadcast = None
    elif type(broadcast) is not bool:
        invalid += 1
        broadcast = None

    name = raw.get("name")
    if "name" not in raw:
        missing += 1
    elif _string(name):
        redacted += 1
    else:
        invalid += 1

    security = raw.get("security")
    if "security" not in raw:
        missing += 1
        security = None
    elif not _int(security, (0, 2, 3)):
        invalid += 1
        security = None

    personal_present = "pskSetting" in raw
    enterprise_present = "entSetting" in raw
    for key, allowed, text_fields, modes in (
        ("pskSetting", _PSK, {"securityKey"}, (("versionPsk", (1, 2, 3)),
                                                    ("encryptionPsk", (1, 3)))),
        ("entSetting", _ENT, {"radiusProfileId"}, (("versionEnt", (1, 2, 3)),
                                                        ("encryptionEnt", (1, 3)))),
    ):
        section = raw.get(key)
        if key not in raw:
            continue
        if not isinstance(section, dict) or len(section) > 12:
            invalid += 1
            continue
        unknown += sum(1 for field in section if field not in allowed)
        for field in text_fields:
            if field in section:
                redacted += 1
                if not _string(section[field]):
                    invalid += 1
        for field, values in modes:
            if field in section and not _int(section[field], values):
                invalid += 1

    vlan_mode = custom_mode = None
    vlan_id_present = bridge_vlan_present = network_binding_present = False
    vlan = raw.get("vlanSetting")
    if "vlanSetting" not in raw:
        missing += 1
    elif not isinstance(vlan, dict) or len(vlan) > 8:
        invalid += 1
    else:
        unknown += sum(1 for field in vlan if field not in _VLAN)
        if "mode" not in vlan:
            missing += 1
        elif _int(vlan["mode"], (0, 1)):
            vlan_mode = vlan["mode"]
        else:
            invalid += 1
        custom = vlan.get("customConfig")
        if "customConfig" in vlan:
            if not isinstance(custom, dict) or len(custom) > 12:
                invalid += 1
            else:
                unknown += sum(1 for field in custom if field not in _VLAN_CUSTOM)
                if "customMode" not in custom:
                    missing += 1
                elif _int(custom["customMode"], (0, 1)):
                    custom_mode = custom["customMode"]
                else:
                    invalid += 1
                for field in ("lanNetworkId", "bridgeVlan", "vlanId"):
                    if field not in custom:
                        continue
                    value = custom[field]
                    if field == "lanNetworkId":
                        redacted += 1
                        network_binding_present = True
                        if not _string(value):
                            invalid += 1
                    else:
                        if type(value) is not int or not 0 <= value <= 4095:
                            invalid += 1
                        if field == "vlanId":
                            vlan_id_present = True
                        else:
                            bridge_vlan_present = True

    return {
        "status": "ok", "resource": "ap_management_ssid",
        "enabled": enabled, "broadcast_enabled": broadcast,
        "security_mode_code": security, "personal_settings_present": personal_present,
        "enterprise_settings_present": enterprise_present, "vlan_mode_code": vlan_mode,
        "custom_vlan_mode_code": custom_mode, "vlan_id_present": vlan_id_present,
        "bridge_vlan_present": bridge_vlan_present,
        "network_binding_present": network_binding_present,
        "redacted_field_count": redacted, "unknown_field_count": unknown,
        "invalid_field_count": invalid, "missing_field_count": missing,
        "partial": bool(missing or invalid or unknown),
    }
