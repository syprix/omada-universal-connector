"""Safe selected SSID configuration fields for one bound WLAN group."""
from __future__ import annotations

from collections.abc import Mapping


class SiteWlanGroupSsidConfigError(ValueError):
    pass


def project_site_wlan_group_ssid_config(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 256:
        raise SiteWlanGroupSsidConfigError("invalid SSID detail")

    result: dict[str, object] = {
        "status": "ok",
        "resource": "site_wlan_group_ssid_config_summary",
        "scope": "selected_ssid_in_selected_wlan_group",
    }
    missing = invalid = 0
    unknown_bits = False

    enabled = value.get("ssidEnable")
    if "ssidEnable" not in value:
        missing += 1
    elif type(enabled) is not bool:
        invalid += 1
    else:
        result["ssid_enabled"] = enabled

    band = value.get("band")
    if "band" not in value:
        missing += 1
    elif type(band) is not int or not 0 <= band <= 7:
        invalid += 1
    else:
        result["band_enabled"] = {
            "2.4ghz": bool(band & 1),
            "5ghz": bool(band & 2),
            "6ghz": bool(band & 4),
        }

    device_type = value.get("deviceType")
    if "deviceType" not in value:
        missing += 1
    elif type(device_type) is not int or device_type < 0:
        invalid += 1
    else:
        result["device_type_enabled"] = {
            "eap": bool(device_type & 1),
            "gateway": bool(device_type & 2),
        }
        unknown_bits = bool(device_type & ~3)
        result["device_type_unknown_bits_present"] = unknown_bits

    result.update({
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "partial": bool(missing or invalid or unknown_bits),
    })
    if invalid:
        raise SiteWlanGroupSsidConfigError("invalid documented field")
    return result
