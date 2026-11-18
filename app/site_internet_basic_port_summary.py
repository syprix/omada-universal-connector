"""Redacted counts for the site's Internet basic port configuration."""

from __future__ import annotations

from collections.abc import Mapping


class SiteInternetBasicPortSummaryError(ValueError):
    """The Internet basic port configuration has an invalid shape."""


_RESULT_FIELDS = frozenset(("preConfiguration", "gatewayModel", "portList", "interval"))
_PORT_FIELDS = frozenset(("portId", "portName", "portMode", "portType"))
_MAX_PORTS = 128
_MAX_INT32 = 2_147_483_647


def project_site_internet_basic_ports(value: object) -> dict[str, object]:
    """Validate common documented fields and aggregate port codes only."""
    if not isinstance(value, Mapping) or len(value) > 16:
        raise SiteInternetBasicPortSummaryError("Internet basic info must be an object")

    missing = invalid = unknown = 0
    for field in _RESULT_FIELDS:
        if field not in value:
            missing += 1
    unknown += sum(field not in _RESULT_FIELDS for field in value)

    preconfiguration: bool | None = None
    raw_preconfiguration = value.get("preConfiguration")
    if type(raw_preconfiguration) is bool:
        preconfiguration = raw_preconfiguration
    elif "preConfiguration" in value:
        invalid += 1

    model_reported = "gatewayModel" in value
    model = value.get("gatewayModel")
    if model_reported and (type(model) is not int or not -_MAX_INT32 <= model <= _MAX_INT32):
        invalid += 1
        model_reported = False

    interval: int | None = None
    raw_interval = value.get("interval")
    if type(raw_interval) is int and 0 <= raw_interval <= _MAX_INT32:
        interval = raw_interval
    elif "interval" in value:
        invalid += 1

    modes = {"0": 0, "1": 0}
    types = {"0": 0, "1": 0}
    unknown_modes = unknown_types = 0
    unreported_modes = unreported_types = 0
    valid_ports = 0
    port_list = value.get("portList")
    truncated = False
    reported_ports: int | None = None
    if isinstance(port_list, list):
        reported_ports = len(port_list)
        if len(port_list) > _MAX_PORTS:
            truncated = True
            invalid += 1
            port_list = port_list[:_MAX_PORTS]
        for row in port_list:
            if not isinstance(row, Mapping) or len(row) > 8:
                invalid += 1
                unreported_modes += 1
                unreported_types += 1
                continue
            valid_ports += 1
            unknown += sum(field not in _PORT_FIELDS for field in row)
            for source, counts, unreported, unknown_box in (
                ("portMode", modes, "mode", "mode"),
                ("portType", types, "type", "type"),
            ):
                if source not in row:
                    if unreported == "mode":
                        unreported_modes += 1
                    else:
                        unreported_types += 1
                    continue
                raw = row[source]
                if type(raw) is not int:
                    invalid += 1
                    if unreported == "mode":
                        unreported_modes += 1
                    else:
                        unreported_types += 1
                elif str(raw) in counts:
                    counts[str(raw)] += 1
                elif unknown_box == "mode":
                    unknown_modes += 1
                else:
                    unknown_types += 1
    elif "portList" in value:
        invalid += 1

    return {
        "data": {
            "preconfiguration_enabled": preconfiguration,
            "gateway_model_reported": model_reported,
            "online_detection_interval_seconds": interval,
            "reported_port_count": reported_ports,
            "valid_port_record_count": valid_ports,
            "port_mode_code_counts": modes,
            "unknown_port_mode_code_count": unknown_modes,
            "unreported_port_mode_count": unreported_modes,
            "port_type_code_counts": types,
            "unknown_port_type_code_count": unknown_types,
            "unreported_port_type_count": unreported_types,
            "truncated": truncated,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or unknown_modes or
                        unknown_types or unreported_modes or unreported_types or truncated),
    }
