"""Common attack-defense settings shared by the three site API exports."""

from __future__ import annotations

from collections.abc import Mapping


class SiteAttackDefenseSummaryError(ValueError):
    """The controller response has an invalid outer shape."""


_BOOLEAN_FIELDS = (
    "existIcmpTimestampRequestReject", "existLargePingThreshold",
    "existTcpScanReject", "icmpConnEnable", "icmpSrcEnable",
    "icmpTimestampRequestReject", "largePingEnable", "pingDeathEnable",
    "pingWanEnable", "specifiedOptionEnable",
    "supportIcmpTimestampRequestReject", "supportLargePingThreshold",
    "supportTcpScanReject", "tcpConnEnable", "tcpFinNoAckEnable",
    "tcpScanEnable", "tcpScanReject", "tcpSrcEnable", "tcpSynFinEnable",
    "udpConnEnable", "udpSrcEnable", "winNukeAttackEnable",
)
_INTEGER_FIELDS = {
    "icmpConnLimit": (100, 99_999),
    "icmpSrcLimit": (100, 99_999),
    "largePingThreshold": (28, 65_535),
    "tcpConnLimit": (100, 99_999),
    "tcpSrcLimit": (100, 99_999),
    "udpConnLimit": (100, 99_999),
    "udpSrcLimit": (100, 99_999),
}
_COMMON_FIELDS = frozenset(_BOOLEAN_FIELDS) | frozenset(_INTEGER_FIELDS)


def project_site_attack_defense_summary(result: object) -> dict[str, object]:
    """Return only the 29 fields with matching types in all source exports.

    ``specifiedOption`` has conflicting schemas and ``featureDescription`` is
    absent from one export, so both are deliberately counted as omitted.
    """
    if not isinstance(result, Mapping) or len(result) > 64:
        raise SiteAttackDefenseSummaryError("result must be a bounded object")

    data: dict[str, object] = {}
    missing = invalid = 0
    for key in _BOOLEAN_FIELDS:
        if key not in result:
            missing += 1
        elif isinstance(result[key], bool):
            data[key] = result[key]
        else:
            invalid += 1

    for key, (minimum, maximum) in _INTEGER_FIELDS.items():
        if key not in result:
            missing += 1
            continue
        value = result[key]
        if (not isinstance(value, int) or isinstance(value, bool) or
                not -(2**31) <= value < 2**31 or not minimum <= value <= maximum):
            invalid += 1
        else:
            data[key] = value

    unknown = sum(key not in _COMMON_FIELDS for key in result)
    return {
        "data": data,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
