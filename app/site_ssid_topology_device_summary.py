"""Count SSID topology associations using only same-site device inventory classes."""
from __future__ import annotations

import re
from collections.abc import Mapping


class SiteSsidTopologyDeviceError(ValueError):
    pass


_MAC = re.compile(r"(?i)^(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}$")


def _mac_key(value: str) -> str:
    return re.sub(r"[:-]", "", value).casefold()


def _device_class(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.strip().casefold().split())
    if normalized in {"ap", "access point", "accesspoint"}:
        return "ap"
    if normalized in {"gateway", "router", "gw"}:
        return "gateway"
    if normalized in {"switch", "sw"}:
        return "switch"
    if normalized == "olt":
        return "olt"
    return None


def project_site_ssid_topology_devices(
    device_macs: object,
    inventory_mac_by_ref: Mapping[str, str],
    inventory_type_by_ref: Mapping[str, str],
) -> dict[str, object]:
    if not isinstance(device_macs, list) or len(device_macs) > 4_096:
        raise SiteSsidTopologyDeviceError("topology_rows_invalid")
    if (not isinstance(inventory_mac_by_ref, Mapping) or
            not isinstance(inventory_type_by_ref, Mapping) or
            len(inventory_mac_by_ref) > 20_000 or len(inventory_type_by_ref) > 20_000):
        raise SiteSsidTopologyDeviceError("inventory_invalid")

    classes_by_mac: dict[str, str | None] = {}
    ambiguous_inventory: set[str] = set()
    for ref, mac in inventory_mac_by_ref.items():
        if (not isinstance(ref, str) or not isinstance(mac, str) or not _MAC.fullmatch(mac)):
            continue
        label = _device_class(inventory_type_by_ref.get(ref))
        key = _mac_key(mac)
        if key in classes_by_mac:
            ambiguous_inventory.add(key)
        else:
            classes_by_mac[key] = label

    seen: set[str] = set()
    counts = {"ap": 0, "gateway": 0, "switch": 0, "olt": 0}
    unmatched = duplicate = unknown_type = ambiguous = invalid = 0
    partial = False
    for raw_mac in device_macs:
        if not isinstance(raw_mac, str) or len(raw_mac) > 32 or not _MAC.fullmatch(raw_mac):
            invalid += 1
            partial = True
            continue
        key = _mac_key(raw_mac)
        if key in seen:
            duplicate += 1
            partial = True
            continue
        seen.add(key)
        if key in ambiguous_inventory:
            ambiguous += 1
            partial = True
            continue
        if key not in classes_by_mac:
            unmatched += 1
            partial = True
            continue
        label = classes_by_mac[key]
        if label is None:
            unknown_type += 1
            partial = True
            continue
        counts[label] += 1

    return {
        "topology_device_count": len(seen),
        "matched_device_count": sum(counts.values()),
        "device_class_counts": counts,
        "unmatched_topology_device_count": unmatched,
        "unknown_device_class_count": unknown_type,
        "ambiguous_inventory_count": ambiguous,
        "duplicate_entry_count": duplicate,
        "invalid_entry_count": invalid,
        "partial": partial,
    }
