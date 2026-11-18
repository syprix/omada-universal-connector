"""Redacted, validated summary of site SNMP configuration."""

from __future__ import annotations

from collections.abc import Mapping


class SiteSnmpError(ValueError):
    """The controller returned an invalid SNMP settings response."""


_ENABLE_FIELDS = {
    "snmpV1V2CEnable": "snmp_v1_v2c_enabled",
    "snmpV3Enable": "snmp_v3_enabled",
}
_MODE_FIELDS = {
    "securityLevel": ("security_level_code", frozenset((0, 1, 2))),
    "authMode": ("authentication_mode_code", frozenset((1, 2))),
    "privacyMode": ("privacy_mode_code", frozenset((1, 2))),
}
_REDACTED_FIELDS = frozenset((
    "communityString", "username", "password", "privacyPassword",
    "location", "contact",
))
_KNOWN_FIELDS = frozenset((*_ENABLE_FIELDS, *_MODE_FIELDS, *_REDACTED_FIELDS))


def project_site_snmp(value: object) -> dict[str, object]:
    """Expose only SNMP protocol and security mode codes; discard private text."""
    if not isinstance(value, Mapping) or len(value) > 32:
        raise SiteSnmpError("SNMP settings must be an object")

    missing = invalid = 0
    output: dict[str, object] = {}
    for source, target in _ENABLE_FIELDS.items():
        if source not in value:
            missing += 1
            output[target] = None
        elif type(value[source]) is not bool:
            invalid += 1
            output[target] = None
        else:
            output[target] = value[source]

    for source, (target, allowed) in _MODE_FIELDS.items():
        if source not in value:
            output[target] = None
        elif type(value[source]) is not int or value[source] not in allowed:
            invalid += 1
            output[target] = None
        else:
            output[target] = value[source]

    for field in _REDACTED_FIELDS:
        if field in value:
            if not isinstance(value[field], str):
                invalid += 1
    unknown = sum(key not in _KNOWN_FIELDS for key in value)
    return {
        "data": output,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
