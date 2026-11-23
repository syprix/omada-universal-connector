"""Redacted aggregate counts for configured Gateway QoS service profiles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


class GatewayQosServiceProfilesError(ValueError):
    """Raised when a service-profile page contains invalid documented fields."""


_PROTOCOLS = {
    0: "tcp",
    1: "udp",
    2: "tcp_udp",
    3: "icmp",
    4: "other",
}


def summarize_gateway_qos_service_profiles(
        rows: Sequence[object], *, omitted_profile_count: int = 0
        ) -> dict[str, object]:
    if (not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or
            type(omitted_profile_count) is not int or omitted_profile_count < 0):
        raise GatewayQosServiceProfilesError("invalid page input")

    default_count = 0
    non_default_count = 0
    unknown_default_count = 0
    protocol_counts = {name: 0 for name in _PROTOCOLS.values()}
    unreported_protocol_count = 0
    unclassified_protocol_count = 0
    for row in rows:
        if not isinstance(row, Mapping):
            raise GatewayQosServiceProfilesError("invalid profile row")
        default = row.get("defaultProfile")
        if default is True:
            default_count += 1
        elif default is False:
            non_default_count += 1
        elif default is None:
            unknown_default_count += 1
        else:
            raise GatewayQosServiceProfilesError("invalid default flag")

        protocol = row.get("protocol")
        if protocol is None:
            unreported_protocol_count += 1
        elif type(protocol) is not int:
            raise GatewayQosServiceProfilesError("invalid protocol")
        elif protocol in _PROTOCOLS:
            protocol_counts[_PROTOCOLS[protocol]] += 1
        else:
            unclassified_protocol_count += 1

    partial = bool(omitted_profile_count or unknown_default_count or
                   unreported_protocol_count or unclassified_protocol_count)
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_gateway_qos_service_profiles_summary",
        "partial": partial,
        "profile_count": len(rows),
        "omitted_profile_count": omitted_profile_count,
        "default_profile_count": default_count,
        "non_default_profile_count": non_default_count,
        "unreported_default_flag_count": unknown_default_count,
        "protocol_profile_counts": protocol_counts,
        "unreported_protocol_count": unreported_protocol_count,
        "unclassified_protocol_count": unclassified_protocol_count,
        "scope": "configured_service_profiles_only",
    }
