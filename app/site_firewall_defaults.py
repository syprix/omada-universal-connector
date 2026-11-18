"""Validated projection of documented site firewall defaults."""

from __future__ import annotations

from collections.abc import Mapping


class SiteFirewallDefaultsError(ValueError):
    """The controller returned an invalid firewall-default response."""


_TIMEOUT_FIELDS = (
    "icmp", "other", "tcpClose", "tcpCloseWait", "tcpEstablished",
    "tcpFinWait", "tcpLastAck", "tcpSynReceive", "tcpSynSent",
    "tcpTimeWait", "udpOther", "udpStream",
)
_FLAG_FIELDS = ("broadcastPing", "receiveRedirects", "sendRedirects", "synCookies")
_FIELDS = frozenset((*_TIMEOUT_FIELDS, *_FLAG_FIELDS))


def project_site_firewall_defaults(value: object) -> dict[str, object]:
    """Return source-documented timeout defaults and flags without extra fields."""
    if not isinstance(value, Mapping) or len(value) > 32:
        raise SiteFirewallDefaultsError("firewall defaults must be an object")

    missing = invalid = unknown = 0
    timeouts: dict[str, int] = {}
    flags: dict[str, bool] = {}
    for field in _TIMEOUT_FIELDS:
        if field not in value:
            missing += 1
            continue
        item = value[field]
        if type(item) is not int or not 1 <= item <= 2_097_151:
            invalid += 1
            continue
        timeouts[field] = item
    for field in _FLAG_FIELDS:
        if field not in value:
            missing += 1
            continue
        item = value[field]
        if not isinstance(item, bool):
            invalid += 1
            continue
        flags[field] = item
    unknown = sum(key not in _FIELDS for key in value)
    return {
        "data": {"timeouts": timeouts, "flags": flags},
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
