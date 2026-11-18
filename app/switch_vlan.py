"""Strict, side-effect-free projection of switch network-detail pages."""
from __future__ import annotations

import re
from collections.abc import Callable


class SwitchVlanProjectionError(ValueError):
    """The documented page or one of its projected fields is invalid."""


_NETWORK_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_OPAQUE_REF = re.compile(r"[0-9a-f]{24}")
_STANDARD_PORT = re.compile(r"[0-9]{1,4}/[0-9]{1,4}/[0-9]{1,4}")
_PORT_FIELDS = (
    ("nativePorts", "native_port_numbers"),
    ("tagPorts", "tagged_port_numbers"),
    ("untagPorts", "untagged_port_numbers"),
)
_LAG_FIELDS = ("nativeLags", "tagLags", "untagLags")
_STANDARD_PORT_FIELDS = ("nativeStPorts", "tagStPorts", "untagStPorts")


def project_switch_networks_page(
    payload: object,
    network_ref_for_id: Callable[[str], str],
    *,
    page: int,
    page_size: int,
    max_entries: int = 256,
) -> dict[str, object]:
    """Project one documented `networks-detail` page without network access.

    Only VLAN IDs, integer port numbers, and callback-issued opaque network
    references are returned. The documented endpoint has no link-status field.
    """
    if (type(page) is not int or page < 1 or type(page_size) is not int or
            not 1 <= page_size <= 1000 or type(max_entries) is not int or
            not 1 <= max_entries <= 10000):
        raise SwitchVlanProjectionError("pagination_invalid")
    if not callable(network_ref_for_id) or not isinstance(payload, dict):
        raise SwitchVlanProjectionError("response_invalid")
    error_code = payload.get("errorCode")
    if type(error_code) is not int or error_code != 0:
        raise SwitchVlanProjectionError("response_invalid")
    grid = payload.get("result")
    if not isinstance(grid, dict):
        raise SwitchVlanProjectionError("response_invalid")
    rows = grid.get("data")
    total = grid.get("totalRows")
    current_page = grid.get("currentPage")
    current_size = grid.get("currentSize")
    if (not isinstance(rows, list) or len(rows) > page_size or
            type(total) is not int or not 0 <= total <= max_entries or
            type(current_page) is not int or current_page != page or
            type(current_size) is not int or current_size not in (len(rows), page_size) or
            total < len(rows)):
        raise SwitchVlanProjectionError("pagination_invalid")

    items = project_switch_network_rows(rows, network_ref_for_id, max_entries=max_entries)["items"]
    return {"status": "ok", "resource": "switch_vlan_networks", "page": page,
            "page_size": page_size, "total_count": total, "count": len(items), "items": items}


def project_switch_network_rows(
    rows: object,
    network_ref_for_id: Callable[[str], str],
    *,
    max_entries: int = 256,
) -> dict[str, object]:
    """Project already-paginated rows returned by the connector page reader."""
    if (not callable(network_ref_for_id) or not isinstance(rows, list) or
            type(max_entries) is not int or not 1 <= max_entries <= 10000 or
            len(rows) > max_entries):
        raise SwitchVlanProjectionError("response_invalid")
    items = [_project_row(row, network_ref_for_id) for row in rows]
    return {"status": "ok", "resource": "switch_vlan_networks", "count": len(items),
            "items": items}


def _project_row(row: object, network_ref_for_id: Callable[[str], str]) -> dict[str, object]:
    if not isinstance(row, dict):
        raise SwitchVlanProjectionError("row_invalid")
    raw_id = row.get("id")
    if not isinstance(raw_id, str) or not _NETWORK_ID.fullmatch(raw_id):
        raise SwitchVlanProjectionError("row_invalid")
    info = row.get("portLagNetworkInfo")
    if info is not None and not isinstance(info, dict):
        raise SwitchVlanProjectionError("row_invalid")
    info = info if isinstance(info, dict) else {}

    vlan = row.get("vlan")
    nested_vlan = info.get("vlan")
    if vlan is None:
        vlan = nested_vlan
    if type(vlan) is not int or not 1 <= vlan <= 4094:
        raise SwitchVlanProjectionError("vlan_invalid")
    if nested_vlan is not None and (type(nested_vlan) is not int or nested_vlan != vlan):
        raise SwitchVlanProjectionError("vlan_invalid")

    try:
        network_ref = _opaque_network_ref(network_ref_for_id(raw_id))
    except SwitchVlanProjectionError:
        raise
    except Exception as exc:
        raise SwitchVlanProjectionError("reference_invalid") from exc
    item: dict[str, object] = {"network_ref": network_ref, "vlan_id": vlan}
    for source, target in _PORT_FIELDS:
        value = info.get(source, [])
        if not isinstance(value, list) or len(value) > 256:
            raise SwitchVlanProjectionError("ports_invalid")
        ports: list[int] = []
        seen: set[int] = set()
        for port in value:
            if type(port) is not int or not 1 <= port <= 4096 or port in seen:
                raise SwitchVlanProjectionError("ports_invalid")
            seen.add(port)
            ports.append(port)
        item[target] = ports

    for source in _LAG_FIELDS:
        value = info.get(source, [])
        if (not isinstance(value, list) or len(value) > 256 or
                any(type(lag) is not int or not 1 <= lag <= 4096 for lag in value)):
            raise SwitchVlanProjectionError("ports_invalid")
    for source in _STANDARD_PORT_FIELDS:
        value = info.get(source, [])
        if (not isinstance(value, list) or len(value) > 256 or
                any(not isinstance(port, str) or not _STANDARD_PORT.fullmatch(port) for port in value)):
            raise SwitchVlanProjectionError("ports_invalid")

    return item


def _opaque_network_ref(value: object) -> str:
    if not isinstance(value, str) or not _OPAQUE_REF.fullmatch(value):
        raise SwitchVlanProjectionError("reference_invalid")
    return value
