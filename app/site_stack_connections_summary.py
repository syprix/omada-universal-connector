"""Redacted site stack membership and LLDP neighbor coverage."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Callable

try:
    from .lldp_neighbors import LldpNeighborProjectionError, project_lldp_neighbor_rows
except ImportError:  # direct execution in the image
    from lldp_neighbors import LldpNeighborProjectionError, project_lldp_neighbor_rows


class SiteStackConnectionsError(ValueError):
    """Stack or LLDP source data is outside the safe projection bounds."""


_MAC = re.compile(r"(?:[0-9A-Fa-f]{2}(?P<sep>[:-])){5}[0-9A-Fa-f]{2}\Z")
_MAX_STACKS = 32
_MAX_MEMBERS = 64
_MAX_NEIGHBORS = 64


def _mac_key(value: object) -> str | None:
    if type(value) is not str:
        return None
    match = _MAC.fullmatch(value)
    if match is None:
        return None
    sep = match.group("sep")
    if any(value[index] != sep for index in (2, 5, 8, 11, 14)):
        return None
    return value.replace(sep, "").lower()


def summarize_site_stack_connections(
    stack_rows: object,
    switch_macs: object,
    stack_ref_for: Callable[[str], str],
    neighbor_rows_by_stack_ref: Mapping[str, object],
    *,
    stack_list_omitted: int = 0,
    neighbor_omitted_by_stack_ref: Mapping[str, int] | None = None,
    source_errors: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Join declared stack members to the fresh site inventory and count LLDP rows.

    Neighbor identities and labels are never returned. The stack LLDP contract
    does not guarantee that its `deviceId` follows the inventory MAC format, so
    these rows are coverage indicators rather than inferred topology links.
    """
    if not isinstance(stack_rows, list) or len(stack_rows) > 4096:
        raise SiteStackConnectionsError("stack_rows_invalid")
    if (not isinstance(switch_macs, Mapping) or len(switch_macs) > 8192 or
            type(stack_list_omitted) is not int or stack_list_omitted < 0):
        raise SiteStackConnectionsError("inventory_invalid")
    omitted_neighbors = dict(neighbor_omitted_by_stack_ref or {})
    errors = dict(source_errors or {})
    mac_refs: dict[str, list[str]] = {}
    for switch_ref, mac in switch_macs.items():
        normalized = _mac_key(mac)
        if type(switch_ref) is str and normalized is not None:
            mac_refs.setdefault(normalized, []).append(switch_ref)
    unique_mac_refs = {mac: refs[0] for mac, refs in mac_refs.items() if len(refs) == 1}
    ambiguous_macs = {mac for mac, refs in mac_refs.items() if len(refs) > 1}

    selected = stack_rows[:_MAX_STACKS]
    omitted_stacks = max(stack_list_omitted, len(stack_rows) - len(selected))
    stacks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    invalid_stacks = duplicate_stacks = invalid_members = 0
    ambiguous_members = unmapped_members = 0
    partial = bool(omitted_stacks or errors)

    for row in selected:
        if not isinstance(row, Mapping):
            invalid_stacks += 1
            continue
        stack_id = row.get("id")
        if type(stack_id) is not str or not stack_id or len(stack_id) > 256:
            invalid_stacks += 1
            continue
        if stack_id in seen_ids:
            duplicate_stacks += 1
            continue
        seen_ids.add(stack_id)
        stack_ref = stack_ref_for(stack_id)
        raw_members = row.get("member")
        if not isinstance(raw_members, list):
            invalid_members += 1
            raw_members = []
        if len(raw_members) > _MAX_MEMBERS:
            invalid_members += len(raw_members) - _MAX_MEMBERS
            raw_members = raw_members[:_MAX_MEMBERS]
        member_refs: set[str] = set()
        for member in raw_members:
            if not isinstance(member, Mapping):
                invalid_members += 1
                continue
            mac = _mac_key(member.get("mac"))
            if mac in ambiguous_macs:
                ambiguous_members += 1
            elif mac is None or mac not in unique_mac_refs:
                unmapped_members += 1
            else:
                member_refs.add(unique_mac_refs[mac])
        status = row.get("status")
        item: dict[str, Any] = {
            "stack_ref": stack_ref,
            "member_switch_refs": sorted(member_refs),
            "member_count": len(raw_members),
            "mapped_member_count": len(member_refs),
        }
        if type(status) is int and status in (0, 1, 2):
            item["status_code"] = status
        else:
            item["status_available"] = False

        if stack_ref in errors:
            item["lldp_status"] = "unavailable"
            item["lldp_error"] = errors[stack_ref]
            item["lldp_port_neighbors"] = []
            partial = True
        elif stack_ref not in neighbor_rows_by_stack_ref:
            item["lldp_status"] = "unavailable"
            item["lldp_port_neighbors"] = []
            partial = True
        else:
            rows = neighbor_rows_by_stack_ref[stack_ref]
            if not isinstance(rows, list) or len(rows) > _MAX_NEIGHBORS:
                raise SiteStackConnectionsError("neighbor_rows_invalid")
            try:
                projected = project_lldp_neighbor_rows(rows)
            except LldpNeighborProjectionError as exc:
                raise SiteStackConnectionsError("neighbor_rows_invalid") from exc
            omitted = omitted_neighbors.get(stack_ref, 0)
            item["lldp_status"] = "partial" if omitted else "ok"
            item["lldp_port_neighbors"] = projected["ports"]
            item["neighbor_entry_count"] = len(rows)
            item["unresolved_neighbor_identity_count"] = len(rows)
            item["omitted_neighbor_entry_count"] = omitted
            if omitted:
                partial = True
        if len(member_refs) != len(raw_members) or "status_code" not in item:
            partial = True
        stacks.append(item)

    if invalid_stacks or duplicate_stacks or invalid_members or ambiguous_members or unmapped_members:
        partial = True
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_stack_connections_summary",
        "stack_limit": _MAX_STACKS,
        "neighbor_page_limit": _MAX_NEIGHBORS,
        "stack_count": len(stacks),
        "stacks_omitted_device_limit": omitted_stacks,
        "invalid_stack_rows": invalid_stacks,
        "duplicate_stack_rows": duplicate_stacks,
        "invalid_stack_members": invalid_members,
        "ambiguous_stack_members": ambiguous_members,
        "unmapped_stack_members": unmapped_members,
        "source_errors": errors,
        "neighbor_linking": "not_inferred; deviceId format is not tied to inventory MACs by the source contract",
        "data": {"stacks": stacks},
        "partial": partial,
    }
