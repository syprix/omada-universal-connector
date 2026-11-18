"""Redacted status of the documented AP SNMP settings."""
from __future__ import annotations


class ApSnmpConfigError(ValueError):
    """The response does not fit the bounded documented SNMP schema."""


def summarize_ap_snmp_config(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 8:
        raise ApSnmpConfigError()
    known = {"type", "location", "contact"}
    unknown = sum(1 for key in raw if key not in known)
    invalid = missing = redacted = 0

    kind = raw.get("type")
    if "type" not in raw:
        missing += 1
        kind = None
    elif type(kind) is not int or kind not in (0, 1):
        invalid += 1
        kind = None

    presence: dict[str, bool] = {}
    for field, maximum in (("location", 128), ("contact", 128)):
        if field not in raw:
            presence[field] = False
            if kind == 1:
                missing += 1
            continue
        value = raw[field]
        redacted += 1
        valid = (isinstance(value, str) and len(value) <= maximum
                 and value.isascii() and not value.startswith(" ")
                 and not value.endswith(" ")
                 and all(" " <= char <= "~" for char in value))
        if field == "contact":
            valid = (isinstance(value, str) and len(value) <= maximum
                     and value.isascii()
                     and all("!" <= char <= "~" for char in value))
        if not valid:
            invalid += 1
        presence[field] = valid and bool(value)

    return {
        "status": "ok", "resource": "ap_snmp_config", "type_code": kind,
        "location_present": presence["location"],
        "contact_present": presence["contact"],
        "redacted_field_count": redacted,
        "unknown_field_count": unknown, "invalid_field_count": invalid,
        "missing_field_count": missing,
        "partial": bool(unknown or invalid or missing),
    }
