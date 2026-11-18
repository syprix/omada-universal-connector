"""Strict, identifier-free projection of Omada switch LLDP neighbor rows.

Pass the ``data`` array from one or more already-bounded pages of the
documented ``OswLldpNeighborVO`` response. The projection reports only the
switch-side integer ``portId`` and how many neighbor rows were returned for
that port; it does not claim anything about ports absent from those rows.
"""
from __future__ import annotations

from typing import Any


class LldpNeighborProjectionError(ValueError):
    """The LLDP response rows do not match the documented safe shape."""


MAX_NEIGHBOR_ROWS = 1000  # The documented API pageSize ceiling.
MAX_PORT_ID = 4096  # Conservative connector bound; the API only specifies int32.


def project_lldp_neighbor_rows(rows: Any) -> dict[str, Any]:
    """Project a bounded list of ``OswLldpNeighborVO`` rows.

    Non-port row values (including device identifiers, names, remote port
    labels, TTL and capabilities) are never inspected or copied. If input
    exceeds the local row bound, the projection marks itself partial and
    reports the number of omitted rows.
    """
    if not isinstance(rows, list):
        raise LldpNeighborProjectionError("response_invalid")

    included = rows[:MAX_NEIGHBOR_ROWS]
    omitted = max(0, len(rows) - MAX_NEIGHBOR_ROWS)
    by_port: dict[int, int] = {}
    for row in included:
        if not isinstance(row, dict):
            raise LldpNeighborProjectionError("response_invalid")
        port_id = row.get("portId")
        if (not isinstance(port_id, int) or isinstance(port_id, bool)
                or not 0 <= port_id <= MAX_PORT_ID):
            raise LldpNeighborProjectionError("response_invalid")
        by_port[port_id] = by_port.get(port_id, 0) + 1

    ports = [
        {"port_id": port_id, "neighbor_present": True, "neighbor_count": count}
        for port_id, count in sorted(by_port.items())
    ]
    return {
        "scope": "ports_with_returned_lldp_neighbors_only",
        "ports": ports,
        "neighbor_entry_count": len(rows),
        "projected_neighbor_entry_count": len(included),
        "port_count": len(ports),
        "omitted_field_count": sum(
            1 for row in included for key in row if key != "portId"),
        "omitted_neighbor_entry_count": omitted,
        "partial": omitted > 0,
    }
