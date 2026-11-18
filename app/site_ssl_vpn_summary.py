"""Redacted projection for the documented, deprecated SSL VPN settings GET."""
from __future__ import annotations

from typing import Any

_FIELDS = {"id", "status", "wanPort", "wanIp", "ipPoolStart", "ipPoolEnd",
           "primaryDns", "secondaryDns", "servicePort", "authType",
           "radiusSetting", "LDAPSetting", "nameLockSetting", "ipLockSetting",
           "exitAtIdle", "exitTime", "totalTraffic", "supportRadius",
           "existRadius", "supportLDAP", "existLdap", "supportByDsLiteAndMapE"}
_BOOL_FIELDS = {"status", "exitAtIdle", "totalTraffic", "supportRadius",
                "existRadius", "supportLDAP", "existLdap", "supportByDsLiteAndMapE"}
_LOCK_FIELDS = {"status", "times", "duration"}

class SiteSslVpnSummaryError(ValueError):
    """Raised when an SSL VPN setting cannot be projected safely."""

def summarize_site_ssl_vpn(result: Any) -> dict[str, object]:
    if not isinstance(result, dict):
        raise SiteSslVpnSummaryError("response_invalid")
    missing = invalid = 0
    unknown = len(set(result) - _FIELDS)
    data: dict[str, object] = {}
    for field, output in (("status", "enabled"), ("exitAtIdle", "idle_disconnect_enabled"),
                          ("totalTraffic", "all_traffic_through_vpn"),
                          ("supportRadius", "radius_supported"),
                          ("existRadius", "radius_configured"),
                          ("supportLDAP", "ldap_supported"),
                          ("existLdap", "ldap_configured"),
                          ("supportByDsLiteAndMapE", "supported_on_ds_lite_or_map_e")):
        value = result.get(field)
        if type(value) is bool:
            data[output] = value
        else:
            data[output] = None
            if field not in result:
                missing += 1
            else:
                invalid += 1
    port = result.get("servicePort")
    if type(port) is int and 1 <= port <= 65535:
        data["service_port"] = port
    else:
        data["service_port"] = None
        if "servicePort" not in result:
            missing += 1
        else:
            invalid += 1
    auth = result.get("authType")
    if type(auth) is int and auth in (0, 1, 2):
        data["authentication_mode"] = {0: "local", 1: "radius", 2: "ldap"}[auth]
    else:
        data["authentication_mode"] = None
        if "authType" not in result:
            missing += 1
        else:
            invalid += 1
    exit_time = result.get("exitTime")
    if type(exit_time) is int and 5 <= exit_time <= 3600:
        data["idle_disconnect_seconds"] = exit_time
    elif "exitTime" not in result and result.get("exitAtIdle") is not True:
        data["idle_disconnect_seconds"] = None
    else:
        data["idle_disconnect_seconds"] = None
        if "exitTime" not in result:
            missing += 1
        else:
            invalid += 1
    for field, output in (("radiusSetting", "radius_config_details_present"),
                          ("LDAPSetting", "ldap_config_details_present")):
        value = result.get(field)
        if isinstance(value, dict):
            data[output] = True
        elif field not in result or value is None:
            data[output] = None
            if field not in result:
                missing += 1
        else:
            data[output] = None
            invalid += 1
    for field, output in (("nameLockSetting", "name_lock_enabled"),
                          ("ipLockSetting", "ip_lock_enabled")):
        value = result.get(field)
        if isinstance(value, dict):
            unknown += len(set(value) - _LOCK_FIELDS)
            active = value.get("status")
            if type(active) is bool:
                data[output] = active
            else:
                data[output] = None
                if "status" not in value:
                    missing += 1
                else:
                    invalid += 1
        elif field not in result or value is None:
            data[output] = None
            if field not in result:
                missing += 1
        else:
            data[output] = None
            invalid += 1
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
