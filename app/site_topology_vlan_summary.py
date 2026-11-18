"""Redacted counts from the topology's available wired VLAN read."""

from __future__ import annotations

from typing import Any

MAX_ROWS = 256
INT32_MAX = 2**31 - 1


class TopologyVlanSummaryError(ValueError):
    """The controller VLAN response is malformed or exceeds projection bounds."""


def _vlan_id(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= INT32_MAX:
        raise TopologyVlanSummaryError("response_invalid")
    return value


def _boolean(value: Any) -> bool:
    if type(value) is not bool:
        raise TopologyVlanSummaryError("response_invalid")
    return value


def project_topology_vlan_summary(result: Any) -> dict[str, object]:
    """Return counts only; never include network names, IDs or VLAN values."""
    if not isinstance(result, dict):
        raise TopologyVlanSummaryError("response_invalid")
    unknown_fields = sum(key != "splitNetworks" for key in result)
    partial = unknown_fields > 0
    networks = result.get("splitNetworks")
    if networks is None:
        return {
            "network_count": None,
            "distinct_vlan_count": None,
            "default_network_count": None,
            "configuring_network_count": None,
            "missing_vlan_id_count": None,
            "unknown_network_field_count": 0,
            "unknown_field_count": unknown_fields,
            "partial": True,
        }
    if not isinstance(networks, list) or len(networks) > MAX_ROWS:
        raise TopologyVlanSummaryError("response_invalid")

    distinct_vlans: set[int] = set()
    vlan_ids_complete = True
    defaults_complete = True
    configuring_complete = True
    defaults = configuring = missing_vlan = unknown_network_fields = 0
    for row in networks:
        if not isinstance(row, dict):
            raise TopologyVlanSummaryError("response_invalid")
        unknown_network_fields += sum(
            key not in {"id", "name", "vlanId", "defaultNetwork", "configuring"}
            for key in row
        )
        if "vlanId" in row:
            distinct_vlans.add(_vlan_id(row["vlanId"]))
        else:
            missing_vlan += 1
            vlan_ids_complete = False
            partial = True
        if "defaultNetwork" in row:
            defaults += int(_boolean(row["defaultNetwork"]))
        else:
            defaults_complete = False
            partial = True
        if "configuring" in row:
            configuring += int(_boolean(row["configuring"]))
        else:
            configuring_complete = False
            partial = True

    partial = partial or unknown_network_fields > 0
    return {
        "network_count": len(networks),
        "distinct_vlan_count": len(distinct_vlans) if vlan_ids_complete else None,
        "default_network_count": defaults if defaults_complete else None,
        "configuring_network_count": configuring if configuring_complete else None,
        "missing_vlan_id_count": missing_vlan,
        "unknown_network_field_count": unknown_network_fields,
        "unknown_field_count": unknown_fields,
        "partial": partial,
    }
