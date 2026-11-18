"""Bounded aggregate for the v2 device-link topology response."""
from __future__ import annotations

from typing import Any

MAX_NODES = 256
MAX_DEPTH = 16
NODE_FIELDS = {
    "type", "name", "mac", "macList", "clientCount", "ipcCount",
    "isAllClients", "uplinkMacList", "multiSwitchDownlinkClient",
    "filterClientCount", "healthScore", "model", "modelVersion", "showModel",
    "specialModel", "deviceSeriesType", "compatible", "ecspFirstVersion",
    "disconnected", "active", "ip", "devTxRate", "devRxRate", "clientHealth",
    "wanPorts", "lanPorts", "stackStatus", "abnormalReason", "stackGroup",
    "stackId", "rdMode2g", "channel2g", "rdMode5g", "channel5g", "rdMode5g2",
    "channel5g2", "rdMode6g", "channel6g", "support5g2", "role", "firmwareVersion",
    "channelNum", "connectedChannel", "wirelessUplink", "successors", "wiredUpInfo",
    "wiredUpInfos", "wirelessUpInfo", "vigiWirelessUpInfo", "portLabels", "description",
    "capability", "status", "statusCategory", "warnNvrFirmware", "clientType",
    "clientVlanId", "omadaDeviceType", "specificOtherType", "existStpLoop",
    "vigiManaged", "ippt", "specificType", "mlagId", "multiSwitchList",
    "multiSwitchNum", "multiSwitchRole", "dadLink", "peerLink", "vrrpLink",
    "vlansAsMaster", "vrrpGroupList",
}
HEALTH_FIELDS = {"good", "fair", "poor", "noData"}


class DeviceLinkTopologyError(ValueError):
    """Raised when topology exceeds the projection's shape bounds."""


def _count(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= 2**31 - 1 else None


def project_device_link_topology(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > MAX_NODES:
        raise DeviceLinkTopologyError("response_invalid")
    seen_nodes = 0
    edge_count = 0
    edge_complete = True
    client_total = ipc_total = 0
    client_complete = ipc_complete = True
    disconnected_count = 0
    disconnected_complete = True
    health_totals = {"good": 0, "fair": 0, "poor": 0, "no_data": 0}
    health_complete = True
    invalid = unknown = 0

    def visit(nodes: list[Any], depth: int) -> None:
        nonlocal seen_nodes, edge_count, edge_complete, client_total, ipc_total
        nonlocal client_complete, ipc_complete, disconnected_count, disconnected_complete
        nonlocal health_complete, invalid, unknown
        if depth > MAX_DEPTH or len(nodes) > MAX_NODES:
            raise DeviceLinkTopologyError("response_invalid")
        for node in nodes:
            if not isinstance(node, dict) or len(node) > len(NODE_FIELDS):
                raise DeviceLinkTopologyError("response_invalid")
            seen_nodes += 1
            if seen_nodes > MAX_NODES:
                raise DeviceLinkTopologyError("response_invalid")
            unknown += len(node.keys() - NODE_FIELDS)
            for field, aggregate, flag in (("clientCount", "client", None),
                                            ("ipcCount", "ipc", None)):
                if field not in node:
                    if aggregate == "client": client_complete = False
                    else: ipc_complete = False
                    continue
                parsed = _count(node[field])
                if parsed is None:
                    invalid += 1
                    if aggregate == "client": client_complete = False
                    else: ipc_complete = False
                elif aggregate == "client": client_total += parsed
                else: ipc_total += parsed
            if "disconnected" in node:
                if type(node["disconnected"]) is bool:
                    disconnected_count += int(node["disconnected"])
                else:
                    invalid += 1
                    disconnected_complete = False
            else:
                disconnected_complete = False
            if "healthScore" in node:
                if type(node["healthScore"]) is int and -(2**31) <= node["healthScore"] <= 2**31 - 1:
                    pass
                else:
                    invalid += 1
            if "clientHealth" in node:
                health = node["clientHealth"]
                if not isinstance(health, dict) or len(health) > len(HEALTH_FIELDS):
                    invalid += 1
                    health_complete = False
                else:
                    unknown += len(health.keys() - HEALTH_FIELDS)
                    for source, target in (("good", "good"), ("fair", "fair"),
                                           ("poor", "poor"), ("noData", "no_data")):
                        if source not in health:
                            health_complete = False
                        else:
                            parsed = _count(health[source])
                            if parsed is None:
                                invalid += 1
                                health_complete = False
                            else:
                                health_totals[target] += parsed
            else:
                health_complete = False
            successors = node.get("successors")
            if successors is None:
                edge_complete = False
            elif not isinstance(successors, list) or len(successors) > MAX_NODES:
                raise DeviceLinkTopologyError("response_invalid")
            else:
                edge_count += len(successors)
                visit(successors, depth + 1)

    visit(result, 1)
    data: dict[str, object] = {"node_count": seen_nodes,
                               "edge_count": edge_count if edge_complete else None,
                               "direct_client_count": client_total if client_complete else None,
                               "ipc_client_count": ipc_total if ipc_complete else None,
                               "disconnected_device_count": disconnected_count if disconnected_complete else None,
                               "health_counts": health_totals if health_complete else None,
                               "invalid_count": invalid,
                               "unknown_field_count": unknown}
    partial = bool(invalid or unknown or not (edge_complete and client_complete and
                                               ipc_complete and disconnected_complete and
                                               health_complete))
    return {"data": data, "partial": partial}
