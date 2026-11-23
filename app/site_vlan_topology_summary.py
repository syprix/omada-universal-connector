"""Summarize a selected VLAN's topology MACs using same-site inventory only."""
from __future__ import annotations

from collections.abc import Mapping

try:
    from .site_ssid_topology_device_summary import (
        SiteSsidTopologyDeviceError, project_site_ssid_topology_devices)
except ImportError:
    from site_ssid_topology_device_summary import (
        SiteSsidTopologyDeviceError, project_site_ssid_topology_devices)


class SiteVlanTopologyError(ValueError):
    pass


def summarize_site_vlan_topology(value: object, *,
                                  inventory_mac_by_ref: Mapping[str, str],
                                  inventory_type_by_ref: Mapping[str, str]
                                  ) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 8:
        raise SiteVlanTopologyError("invalid topology result")
    device_macs = value.get("deviceMacs")
    try:
        projected = project_site_ssid_topology_devices(
            device_macs, inventory_mac_by_ref, inventory_type_by_ref)
    except SiteSsidTopologyDeviceError:
        raise SiteVlanTopologyError("invalid topology MAC list") from None
    unknown_fields = sum(key != "deviceMacs" for key in value)
    projected["unknown_field_count"] = unknown_fields
    projected["partial"] = bool(projected["partial"] or unknown_fields)
    projected["status"] = "ok"
    projected["resource"] = "site_vlan_topology_summary"
    return projected
