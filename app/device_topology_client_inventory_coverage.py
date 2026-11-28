"""Bounded, identity-free field coverage for one adopted device's topology clients."""
from __future__ import annotations

from collections.abc import Mapping

MAX_TOPOLOGY_CLIENT_ROWS = 4_096
_FIELDS = ("mac", "name", "ip", "wireless", "guest", "type", "vendor", "model",
           "devTxRate", "devRxRate", "healthScore", "wiredUpInfo", "wirelessUpInfo",
           "connectedNetwork", "connectedSsid")
_STRINGS = {"mac", "name", "ip", "type", "vendor", "model"}
_BOOLEANS = {"wireless", "guest"}
_NESTED_OBJECTS = {"wiredUpInfo", "wirelessUpInfo", "connectedNetwork", "connectedSsid"}
_INT64_FIELDS = {"devTxRate", "devRxRate"}


class DeviceTopologyClientInventoryError(ValueError):
    """Raised for an unsupported or over-bound topology response."""


def project_device_topology_client_inventory_coverage(rows: object) -> dict[str, object]:
    if not isinstance(rows, list) or len(rows) > MAX_TOPOLOGY_CLIENT_ROWS:
        raise DeviceTopologyClientInventoryError("rows_invalid")
    coverage = {field: {"present": 0, "missing": 0, "type_valid": 0, "invalid": 0}
                for field in _FIELDS}
    unknown = invalid = 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 32 or any(not isinstance(k, str) for k in row):
            invalid += 1
            continue
        unknown += sum(key not in _FIELDS for key in row)
        for field in _FIELDS:
            counts = coverage[field]
            if field not in row:
                counts["missing"] += 1
                continue
            counts["present"] += 1
            value = row[field]
            if field in _STRINGS:
                valid = isinstance(value, str) and len(value) <= 512
            elif field in _BOOLEANS:
                valid = type(value) is bool
            elif field in _NESTED_OBJECTS:
                valid = isinstance(value, Mapping) and len(value) <= 32
            elif field in _INT64_FIELDS:
                valid = type(value) is int and -(1 << 63) <= value <= (1 << 63) - 1
            else:
                valid = type(value) is int and -(1 << 31) <= value <= (1 << 31) - 1
            counts["type_valid"] += int(valid)
            counts["invalid"] += int(not valid)
    partial = bool(invalid or unknown or any(
        counts["invalid"] for counts in coverage.values()))
    return {
        "topology_client_count": len(rows),
        "client_field_coverage": coverage,
        "invalid_row_count": invalid,
        "unknown_field_count": unknown,
        "partial": partial,
        "client_identities_returned": False,
    }
