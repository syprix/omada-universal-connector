"""Bounded summary projection for the documented OLT detail read."""
from __future__ import annotations

from typing import Any


MAX_INT32 = 2_147_483_647
MAX_INT64 = 9_223_372_036_854_775_807
_STATUS_CODES = {0, 1, 10, 11, 12, 13, 14, 15, 16, 17, 20, 21, 22, 23, 24, 25,
                 26, 27, 30, 31, 32, 33, 40, 41, 50}
_STATUS_CATEGORIES = {0, 1, 2, 3, 4}
_DOCUMENTED_FIELDS = {
    "active", "addedInAdvanced", "boundDeviceTemplate", "boundSiteTemplate", "category",
    "compatible", "components", "compoundModel", "cpuUtil", "customId", "customName",
    "description", "devCap", "deviceSeriesType", "deviceTemplateAvailable", "disableHwReset",
    "down", "downlinkList", "dueTime", "dueTimeLeft", "ecspFirstVersion", "eos", "eost",
    "es", "firmwareVersion", "forgetId", "hwVersion", "inWhitelist",
    "initialUnbindingLimit", "ip", "ipv6List", "lastSeen", "latestVersion", "licenseId",
    "licenseStatus", "licenseUnbindingLimit", "location", "mac", "memUtil", "model",
    "modelVersion", "moveSiteId", "name", "omadacId", "onuCount", "publicIp", "remember",
    "rememberDevice", "replaceDeviceInfo", "resource", "showModel", "site", "siteName",
    "siteTemplateId", "siteTemplateName", "sn", "specialModel", "speeds", "status",
    "statusCategory", "supportAnomaly", "supportLocatePort", "tagIds", "templateId",
    "templateName", "type", "up", "uplink", "uptime", "uptimeLong", "version",
}


class OltDetailError(ValueError):
    """Raised when an OLT detail response exceeds its documented shape."""


def _bounded_int(value: Any, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def project_olt_detail(result: Any) -> dict[str, object]:
    """Keep safe operational values; omit identity, location, license and raw topology."""
    if not isinstance(result, dict) or len(result) > 80:
        raise OltDetailError("response_invalid")

    data: dict[str, object] = {}
    invalid = 0
    missing = 0
    unknown = len(set(result) - _DOCUMENTED_FIELDS)

    if result.get("type") is None:
        missing += 1
    elif result["type"] != "olt":
        invalid += 1

    for field, output, allowed in (
        ("status", "status_code", _STATUS_CODES),
        ("statusCategory", "status_category_code", _STATUS_CATEGORIES),
    ):
        value = result.get(field)
        if value is None:
            missing += 1
        elif type(value) is int and value in allowed:
            data[output] = value
        else:
            invalid += 1

    for field, output in (("cpuUtil", "cpu_percent"), ("memUtil", "memory_percent")):
        value = result.get(field)
        if value is None:
            missing += 1
        elif _bounded_int(value, 100):
            data[output] = value
        else:
            invalid += 1

    for field, output in (("uptimeLong", "uptime_seconds"), ("onuCount", "onu_count"),
                          ("down", "traffic_down_bytes"), ("up", "traffic_up_bytes")):
        value = result.get(field)
        if value is None:
            missing += 1
        elif _bounded_int(value, MAX_INT64 if field in {"uptimeLong", "down", "up"} else MAX_INT32):
            data[output] = value
        else:
            invalid += 1

    model = result.get("model")
    if model is None:
        missing += 1
    elif isinstance(model, str) and len(model) <= 128:
        data["model"] = model[:128]
    else:
        invalid += 1

    for field, output in (("firmwareVersion", "firmware_version_present"),
                          ("hwVersion", "hardware_version_present")):
        value = result.get(field)
        if value is None:
            missing += 1
        elif isinstance(value, str) and len(value) <= 256:
            data[output] = bool(value)
        else:
            invalid += 1

    downlinks = result.get("downlinkList")
    if downlinks is None:
        missing += 1
    elif isinstance(downlinks, list) and len(downlinks) <= 256:
        data["downlink_count"] = len(downlinks)
        invalid += sum(not isinstance(row, dict) for row in downlinks)
    else:
        invalid += 1

    return {
        "data": data,
        "partial": bool(missing or invalid or unknown),
        "missing_count": missing,
        "invalid_count": invalid,
        "unknown_field_count": unknown,
        "redacted_field_count": len(set(result) & (_DOCUMENTED_FIELDS - {
            "type", "status", "statusCategory", "cpuUtil", "memUtil", "uptimeLong",
            "onuCount", "down", "up", "model", "firmwareVersion", "hwVersion",
            "downlinkList",
        })),
    }
