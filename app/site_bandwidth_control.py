"""Privacy-preserving summary for the site bandwidth-control settings read."""

from __future__ import annotations

from collections.abc import Mapping


class SiteBandwidthControlError(ValueError):
    """The controller response has an invalid outer shape."""


_PORT_FIELDS = frozenset((
    "portUuid", "upstreamBandwidth", "upstreamBandwidthUnit",
    "downstreamBandwidth", "downstreamBandwidthUnit",
))


def project_site_bandwidth_control(result: object) -> dict[str, object]:
    """Validate the contract and summarize rates without returning port UUIDs."""
    if not isinstance(result, Mapping) or len(result) > 16:
        raise SiteBandwidthControlError("result must be a bounded object")

    missing = invalid = 0
    unknown = sum(key not in {"enable", "thresholdControlEnable", "thresholdValue",
                              "bandwidthPortSettings"} for key in result)

    enabled = result.get("enable")
    if "enable" not in result:
        missing += 1
        enabled = None
    elif not isinstance(enabled, bool):
        invalid += 1
        enabled = None

    threshold_enabled = result.get("thresholdControlEnable")
    if "thresholdControlEnable" in result and not isinstance(threshold_enabled, bool):
        invalid += 1
        threshold_enabled = None

    threshold_value = result.get("thresholdValue")
    if "thresholdValue" in result:
        if (not isinstance(threshold_value, int) or isinstance(threshold_value, bool) or
                not 1 <= threshold_value <= 100):
            invalid += 1
            threshold_value = None
    elif threshold_enabled is True:
        missing += 1
    else:
        threshold_value = None

    raw_ports = result.get("bandwidthPortSettings", [])
    if "bandwidthPortSettings" in result and not isinstance(raw_ports, list):
        invalid += 1
        raw_ports = []
    if len(raw_ports) > 256:
        invalid += 1
        raw_ports = []

    upstream = {"kbps": 0, "mbps": 0}
    downstream = {"kbps": 0, "mbps": 0}
    valid_port_count = 0
    for row in raw_ports:
        if not isinstance(row, Mapping) or len(row) > 12:
            invalid += 1
            continue
        unknown += sum(key not in _PORT_FIELDS for key in row)
        port_uuid = row.get("portUuid")
        if not isinstance(port_uuid, str) or not port_uuid:
            invalid += 1
            continue
        valid = True
        entry_sums: list[tuple[str, int, int]] = []
        for prefix in ("upstream", "downstream"):
            value_key = prefix + "Bandwidth"
            unit_key = prefix + "BandwidthUnit"
            has_value, has_unit = value_key in row, unit_key in row
            if not has_value and not has_unit:
                continue
            value, unit = row.get(value_key), row.get(unit_key)
            if (not has_value or not isinstance(value, int) or isinstance(value, bool) or
                    not 1 <= value <= 9_999_999 or unit not in (1, 2) or
                    isinstance(unit, bool)):
                invalid += 1
                valid = False
                continue
            entry_sums.append((prefix, unit, value))
        if valid:
            valid_port_count += 1
            for prefix, unit, value in entry_sums:
                target = upstream if prefix == "upstream" else downstream
                target["kbps" if unit == 1 else "mbps"] += value

    return {
        "data": {
            "enabled": enabled,
            "threshold_control_enabled": threshold_enabled,
            "threshold_value": threshold_value,
            "returned_port_count": len(raw_ports),
            "valid_port_count": valid_port_count,
            "upstream_bandwidth_totals": upstream,
            "downstream_bandwidth_totals": downstream,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
