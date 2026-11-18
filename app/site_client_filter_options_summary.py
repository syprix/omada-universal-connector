"""Redacted counts of client-list filter options for one site."""
from __future__ import annotations


_FIELDS = {"deviceType", "vendor", "device", "network", "ssid", "deviceDetail"}
_MAX_OPTIONS = 10_000


class ClientFilterOptionsError(ValueError):
    """Invalid or unsafe filter-option response."""


def project_site_client_filter_options_summary(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ClientFilterOptionsError("options_invalid")
    counts = {"device_type_categories": 0, "device_type_values": 0,
              "vendors": 0, "devices": 0, "networks": 0, "ssids": 0,
              "device_details": 0, "stacked_devices": 0}
    redacted = unknown = invalid = 0
    key_map = {"vendor": "vendors", "device": "devices", "network": "networks", "ssid": "ssids"}
    for key in _FIELDS:
        if key not in raw:
            unknown += 1
            continue
        values = raw[key]
        if not isinstance(values, list) or len(values) > _MAX_OPTIONS:
            invalid += 1
            continue
        if key in key_map:
            counts[key_map[key]] = len(values)
            if any(not isinstance(v, str) or len(v) > 256 or any(ord(c) < 32 for c in v)
                   for v in values):
                invalid += 1
                counts[key_map[key]] = sum(isinstance(v, str) and len(v) <= 256 and
                                           all(ord(c) >= 32 for c in v) for v in values)
            redacted += len(values)
        elif key == "deviceType":
            categories = 0
            type_values = 0
            for row in values:
                if not isinstance(row, dict):
                    invalid += 1
                    continue
                if "category" not in row or not isinstance(row.get("type"), list):
                    unknown += 1
                    continue
                category, types = row.get("category"), row["type"]
                if (not isinstance(category, str) or len(category) > 256 or
                        any(ord(c) < 32 for c in category) or len(types) > _MAX_OPTIONS or
                        any(not isinstance(v, str) or len(v) > 256 or any(ord(c) < 32 for c in v)
                            for v in types)):
                    invalid += 1
                    continue
                categories += 1
                type_values += len(types)
                redacted += 1 + len(types)
                unknown += sum(k not in {"category", "type"} for k in row)
            counts["device_type_categories"] = categories
            counts["device_type_values"] = type_values
        else:
            details = 0
            stacked = 0
            for row in values:
                if not isinstance(row, dict):
                    invalid += 1
                    continue
                stack = row.get("stack")
                if stack is not None and not isinstance(stack, bool):
                    invalid += 1
                    continue
                details += 1
                stacked += int(stack is True)
                redacted += sum(k in row and row[k] is not None for k in ("mac", "name", "stackName"))
                unknown += sum(k not in {"mac", "name", "stack", "stackName"} for k in row)
            counts["device_details"] = details
            counts["stacked_devices"] = stacked
    unknown += sum(key not in _FIELDS for key in raw)
    return {**counts, "partial": bool(unknown or invalid),
            "redacted_field_count": redacted,
            "unknown_field_count": unknown,
            "invalid_field_count": invalid}
