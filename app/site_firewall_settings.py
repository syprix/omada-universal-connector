"""Projection for the common site firewall settings read."""

from __future__ import annotations

from collections.abc import Mapping


class SiteFirewallSettingsError(ValueError):
    """The controller response has an invalid outer shape."""


_INTEGER_FIELDS = (
    "icmp", "other", "tcpClose", "tcpCloseWait", "tcpEstablished",
    "tcpFinWait", "tcpLastAck", "tcpSynReceive", "tcpSynSent",
    "tcpTimeWait", "udpOther", "udpStream",
)
_BOOLEAN_FIELDS = ("broadcastPing", "receiveRedirects", "sendRedirects", "synCookies")
_KNOWN_FIELDS = frozenset(_INTEGER_FIELDS + _BOOLEAN_FIELDS)


def project_site_firewall_settings(result: object) -> dict[str, object]:
    if not isinstance(result, Mapping) or len(result) > 32:
        raise SiteFirewallSettingsError("result must be a bounded object")
    data: dict[str, object] = {}
    missing = invalid = 0

    for key in _INTEGER_FIELDS:
        if key not in result:
            missing += 1
            continue
        value = result[key]
        if (not isinstance(value, int) or isinstance(value, bool) or
                not 1 <= value <= 2_097_151):
            invalid += 1
        else:
            data[key] = value

    for key in _BOOLEAN_FIELDS:
        if key not in result:
            missing += 1
        elif isinstance(result[key], bool):
            data[key] = result[key]
        else:
            invalid += 1

    unknown = sum(key not in _KNOWN_FIELDS for key in result)
    return {
        "data": data,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
