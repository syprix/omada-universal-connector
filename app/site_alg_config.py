"""Common site ALG configuration fields from the three API exports."""

from __future__ import annotations

from collections.abc import Mapping


class SiteAlgConfigError(ValueError):
    """The controller response has an invalid outer shape."""


_BOOLEAN_FIELDS = (
    "ftp", "h323", "pptp", "sip", "ipSec", "sipTcp", "sipUdp",
    "sipDirectSignaling", "sipDirectMedia", "sipTimeout",
    "supportSipAlgConfig", "existSipAlgConfig", "existFtpAlgConfig",
)
_REQUIRED_FIELDS = frozenset(("ftp", "h323", "ipSec", "pptp", "sip"))
_ARRAY_FIELDS = ("ftpPorts", "sipPorts")
_TIMEOUT_FIELDS = ("sipSignalingTimeout", "sipMediaTimeout")
_KNOWN_FIELDS = frozenset(_BOOLEAN_FIELDS + _ARRAY_FIELDS + _TIMEOUT_FIELDS)


def project_site_alg_config(result: object) -> dict[str, object]:
    """Project all 17 common response fields with source-specific bounds."""
    if not isinstance(result, Mapping) or len(result) > 32:
        raise SiteAlgConfigError("result must be a bounded object")

    data: dict[str, object] = {}
    missing = invalid = 0
    for key in _BOOLEAN_FIELDS:
        if key not in result:
            missing += int(key in _REQUIRED_FIELDS)
        elif isinstance(result[key], bool):
            data[key] = result[key]
        else:
            invalid += 1

    for key in _ARRAY_FIELDS:
        if key not in result:
            continue
        value = result[key]
        if (not isinstance(value, list) or len(value) > 128 or
                any(not isinstance(port, int) or isinstance(port, bool) or
                    not -(2**31) <= port < 2**31 for port in value)):
            invalid += 1
        else:
            data[key] = list(value)

    for key in _TIMEOUT_FIELDS:
        if key not in result:
            continue
        value = result[key]
        if (not isinstance(value, int) or isinstance(value, bool) or
                not 1 <= value <= 86_400):
            invalid += 1
        else:
            data[key] = value

    unknown = sum(key not in _KNOWN_FIELDS for key in result)
    return {
        "data": data,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
