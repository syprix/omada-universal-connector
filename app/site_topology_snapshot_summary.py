"""Redacted counts from the documented site topology snapshot."""

from __future__ import annotations

from collections.abc import Mapping


class TopologySnapshotError(ValueError):
    """Raised when the topology snapshot cannot be summarized safely."""


def summarize_topology_snapshot(
        result: object, *, max_nodes: int = 10_000,
        max_edges: int = 10_000) -> dict[str, object]:
    if not isinstance(result, Mapping):
        raise TopologySnapshotError("invalid result")
    nodes = result.get("topologyNodes")
    edges = result.get("topologyEdges")
    if (not isinstance(nodes, list) or not isinstance(edges, list) or
            len(nodes) > max_nodes or len(edges) > max_edges):
        raise TopologySnapshotError("invalid topology lists")

    node_refs: set[str] = set()
    nodes_without_ref = 0
    for node in nodes:
        if not isinstance(node, Mapping):
            raise TopologySnapshotError("invalid node")
        ref = node.get("mac")
        if ref is None:
            nodes_without_ref += 1
        elif not isinstance(ref, str) or not ref:
            raise TopologySnapshotError("invalid node reference")
        else:
            node_refs.add(ref)

    blocked_edges = 0
    unblocked_edges = 0
    edges_without_block_state = 0
    missing_endpoint_refs = 0
    unreported_endpoint_refs = 0
    for edge in edges:
        if not isinstance(edge, Mapping):
            raise TopologySnapshotError("invalid edge")
        blocked = edge.get("blocked")
        if blocked is True:
            blocked_edges += 1
        elif blocked is False:
            unblocked_edges += 1
        elif blocked is None:
            edges_without_block_state += 1
        else:
            raise TopologySnapshotError("invalid blocked state")
        for field in ("upLinkMac", "downLinkMac"):
            ref = edge.get(field)
            if ref is None:
                unreported_endpoint_refs += 1
            elif not isinstance(ref, str) or not ref:
                raise TopologySnapshotError("invalid endpoint reference")
            elif ref not in node_refs:
                missing_endpoint_refs += 1

    partial = bool(nodes_without_ref or edges_without_block_state or
                   missing_endpoint_refs or unreported_endpoint_refs)
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_topology_snapshot_summary",
        "partial": partial,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_rows_without_reference_count": nodes_without_ref,
        "blocked_edge_count": blocked_edges,
        "unblocked_edge_count": unblocked_edges,
        "edges_without_block_state_count": edges_without_block_state,
        "missing_endpoint_reference_count": missing_endpoint_refs,
        "unreported_endpoint_reference_count": unreported_endpoint_refs,
        "scope": "documented_topology_snapshot_counts_only",
    }
