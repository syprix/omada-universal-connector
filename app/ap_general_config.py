"""Redacted summary of an inventoried AP's general configuration."""
from __future__ import annotations

import math


class ApGeneralConfigError(ValueError):
    """The general configuration is outside its projection bounds."""


_ROOT = frozenset({"name", "ledSetting", "remoteReset", "wifiControlEnable",
                   "rssiLedSettings", "tagIds", "gpsEnable", "location",
                   "rememberDevice", "disableHwReset"})
_LED = frozenset({"ledId", "threshold"})
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def _int32(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def summarize_ap_general_config(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 16:
        raise ApGeneralConfigError()
    redacted = int("name" in raw)
    unknown = sum(1 for key in raw if key not in _ROOT)
    invalid = missing = 0
    if "name" in raw and (not isinstance(raw["name"], str) or len(raw["name"]) > 128):
        invalid += 1
    scalar: dict[str, object] = {}
    for key in ("ledSetting", "remoteReset", "wifiControlEnable", "gpsEnable",
                "rememberDevice", "disableHwReset"):
        if key not in raw:
            missing += 1
        elif key in ("remoteReset", "wifiControlEnable", "gpsEnable", "disableHwReset"):
            if type(raw[key]) is bool:
                scalar[key] = raw[key]
            else:
                invalid += 1
        elif _int32(raw[key]) and (key != "ledSetting" or raw[key] in (0, 1, 2)) and (
                key != "rememberDevice" or raw[key] in (0, 1, 2)):
            scalar[key] = raw[key]
        else:
            invalid += 1

    tags = raw.get("tagIds")
    if "tagIds" not in raw:
        missing += 1
        tag_count = None
    elif isinstance(tags, list) and len(tags) <= 128 and all(
            isinstance(tag, str) and len(tag) <= 256 for tag in tags):
        tag_count = len(tags)
        redacted += len(tags)
    else:
        invalid += 1
        tag_count = None

    location = raw.get("location")
    if "location" not in raw:
        missing += 1
        location_configured = None
    elif isinstance(location, dict) and len(location) <= 8:
        location_configured = bool(location)
        redacted += sum(1 for key in ("longitude", "latitude", "address", "timestamp")
                        if key in location)
        unknown += sum(1 for key in location if key not in
                       {"longitude", "latitude", "address", "timestamp"})
        if any(key in location and location[key] is not None and
               (not isinstance(location[key], str) or len(location[key]) > 512)
               for key in ("address",)):
            invalid += 1
        for key, limit in (("longitude", 180), ("latitude", 90)):
            value = location.get(key)
            if (key in location and value is not None and
                    (type(value) not in (int, float) or isinstance(value, bool) or
                     abs(value) > limit or not math.isfinite(value))):
                invalid += 1
        if ("timestamp" in location and location["timestamp"] is not None and
                (type(location["timestamp"]) is not int or
                 not 0 <= location["timestamp"] <= 2**63 - 1)):
            invalid += 1
    else:
        invalid += 1
        location_configured = None

    rssi = raw.get("rssiLedSettings")
    if "rssiLedSettings" not in raw:
        missing += 1
        rssi_count = None
        threshold_counts: dict[int, int] = {}
    elif isinstance(rssi, list) and len(rssi) <= 32:
        rssi_count = len(rssi)
        threshold_counts = {}
        redacted += sum(1 for item in rssi
                        if isinstance(item, dict) and "ledId" in item)
        for item in rssi:
            if not isinstance(item, dict) or len(item) > 8:
                invalid += 1
                continue
            if "ledId" in item and (not isinstance(item["ledId"], str) or
                                    len(item["ledId"]) > 128):
                invalid += 1
            unknown += sum(1 for key in item if key not in _LED)
            threshold = item.get("threshold")
            if "threshold" not in item:
                missing += 1
            elif _int32(threshold):
                threshold_counts[threshold] = threshold_counts.get(threshold, 0) + 1
            else:
                invalid += 1
    else:
        invalid += 1
        rssi_count = None
        threshold_counts = {}

    partial = bool(missing or invalid or unknown)
    return {
        "status": "ok", "resource": "ap_general_config", **scalar,
        "tag_count": tag_count, "location_configured": location_configured,
        "rssi_led_setting_count": rssi_count,
        "rssi_threshold_counts": dict(sorted(threshold_counts.items())),
        "redacted_field_count": redacted, "unknown_field_count": unknown,
        "invalid_field_count": invalid, "missing_field_count": missing,
        "partial": partial,
    }
