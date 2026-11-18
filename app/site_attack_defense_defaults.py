"""Validation and bounded projection for site attack-defense defaults."""
from __future__ import annotations

from collections.abc import Mapping


class SiteAttackDefenseDefaultsError(ValueError):
    """The documented attack-defense default response is malformed."""


_BOOLEAN_FIELDS = (
    "tcpConnEnable", "udpConnEnable", "icmpConnEnable", "tcpSrcEnable",
    "udpSrcEnable", "icmpSrcEnable", "tcpScanEnable", "tcpScanReject",
    "pingDeathEnable", "largePingEnable", "pingWanEnable",
    "winNukeAttackEnable", "tcpSynFinEnable", "tcpFinNoAckEnable",
    "specifiedOptionEnable", "icmpTimestampRequestReject",
)
_REQUIRED_BOOLEAN_FIELDS = frozenset((
    "tcpConnEnable", "udpConnEnable", "icmpConnEnable", "tcpSrcEnable",
    "udpSrcEnable", "icmpSrcEnable", "tcpScanEnable", "pingDeathEnable",
    "largePingEnable", "pingWanEnable", "winNukeAttackEnable",
    "tcpSynFinEnable", "tcpFinNoAckEnable", "specifiedOptionEnable",
))
_INTEGER_FIELDS = {
    "tcpConnLimit": (100, 99_999),
    "udpConnLimit": (100, 99_999),
    "icmpConnLimit": (100, 99_999),
    "tcpSrcLimit": (100, 99_999),
    "udpSrcLimit": (100, 99_999),
    "icmpSrcLimit": (100, 99_999),
    "largePingThreshold": (28, 65_535),
}
_SPECIFIED_OPTION_FIELDS = (
    "securityOptionEnable", "recordRouteEnable", "streamEnable",
    "timestampEnable", "noOperationEnable",
)
_ALL_FIELDS = (frozenset(_BOOLEAN_FIELDS) | frozenset(_INTEGER_FIELDS) |
               frozenset(("specifiedOption",)))


def project_site_attack_defense_defaults(result: object) -> dict[str, object]:
    """Preserve documented source names and report absent/invalid/unknown data."""
    if not isinstance(result, Mapping) or len(result) > 32:
        raise SiteAttackDefenseDefaultsError("result must be a bounded object")

    data: dict[str, object] = {}
    missing = invalid = 0
    for key in _BOOLEAN_FIELDS:
        if key not in result:
            missing += key in _REQUIRED_BOOLEAN_FIELDS
        elif isinstance(result[key], bool):
            data[key] = result[key]
        else:
            invalid += 1

    for key, (minimum, maximum) in _INTEGER_FIELDS.items():
        if key not in result:
            continue
        value = result[key]
        if (not isinstance(value, int) or isinstance(value, bool) or
                not -(2**31) <= value < 2**31 or not minimum <= value <= maximum):
            invalid += 1
        else:
            data[key] = value

    if "specifiedOption" in result:
        options = result["specifiedOption"]
        if not isinstance(options, Mapping) or len(options) > 8:
            invalid += 1
        else:
            projected_options: dict[str, bool] = {}
            for key, value in options.items():
                if key not in _SPECIFIED_OPTION_FIELDS:
                    continue
                if isinstance(value, bool):
                    projected_options[key] = value
                else:
                    invalid += 1
            data["specifiedOption"] = projected_options

    unknown = sum(key not in _ALL_FIELDS for key in result)
    if isinstance(result.get("specifiedOption"), Mapping):
        unknown += sum(key not in _SPECIFIED_OPTION_FIELDS
                       for key in result["specifiedOption"])
    return {
        "data": data,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
