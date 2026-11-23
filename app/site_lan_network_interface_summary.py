"""Redacted summary of LAN network/interface categories."""
from __future__ import annotations

from collections.abc import Mapping


class SiteLanNetworkInterfaceSummaryError(ValueError):
    pass


def summarize_site_lan_network_interfaces(rows: object,
                                          interface_type: int | None) -> dict[str, object]:
    if (not isinstance(rows, list) or len(rows) > 10_000 or
            interface_type not in (None, 0)):
        raise SiteLanNetworkInterfaceSummaryError("input_invalid")
    purposes = {"vlan": 0, "interface": 0, "unknown": 0}
    vlan_types = {"single": 0, "multiple": 0, "unknown": 0}
    applications = {"gateway_and_switch": 0, "switch_only": 0, "unknown": 0}
    interface_associations = {"identifier_count": 0, "rows_missing": 0}
    subnet_presence = {"present": 0, "missing": 0}
    field_presence = {key: {"present": 0, "missing": 0} for key in (
        "name", "purpose", "igmp_snooping")}
    partial = False
    known = {"id", "name", "purpose", "interfaceIds", "vlanType", "vlans", "vlan",
             "application", "gatewaySubnet", "dhcpSettingsVO", "domain",
             "igmpSnoopEnable", "mldSnoopEnable", "dhcpL2RelayEnable", "dhcpGuard",
             "dhcpv6Guard", "portal", "portalId", "portalName", "accessControlRule",
             "rateLimit", "lanNeworkIpv6Config", "allLan", "existMultiVlan",
             "existRA", "existCustomDhcpOption", "existDhcpNextServer",
             "existArpDetection", "primary"}
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 64:
            raise SiteLanNetworkInterfaceSummaryError("row_invalid")
        if set(row) - known:
            partial = True
        for key in ("id", "name", "vlans", "gatewaySubnet", "domain", "portalId", "portalName"):
            if key in row and (not isinstance(row[key], str) or len(row[key]) > 4096):
                raise SiteLanNetworkInterfaceSummaryError("field_invalid")
        purpose = row.get("purpose")
        if purpose is None:
            field_presence["purpose"]["missing"] += 1
            purposes["unknown"] += 1
            partial = True
        elif type(purpose) is not int:
            raise SiteLanNetworkInterfaceSummaryError("field_invalid")
        else:
            field_presence["purpose"]["present"] += 1
            purposes[{0: "vlan", 1: "interface"}.get(purpose, "unknown")] += 1
            partial |= purpose not in (0, 1)

        name = row.get("name")
        if name is None:
            field_presence["name"]["missing"] += 1
            partial = True
        else:
            field_presence["name"]["present"] += 1

        igmp = row.get("igmpSnoopEnable")
        if igmp is None:
            field_presence["igmp_snooping"]["missing"] += 1
            partial = True
        elif type(igmp) is not bool:
            raise SiteLanNetworkInterfaceSummaryError("field_invalid")
        else:
            field_presence["igmp_snooping"]["present"] += 1

        if purpose == 1:
            if not row.get("gatewaySubnet"):
                partial = True
            vlan_type = row.get("vlanType")
            if vlan_type is None:
                vlan_types["unknown"] += 1
                partial = True
            elif type(vlan_type) is not int:
                raise SiteLanNetworkInterfaceSummaryError("field_invalid")
            else:
                vlan_types[{0: "single", 1: "multiple"}.get(vlan_type, "unknown")] += 1
                partial |= vlan_type not in (0, 1)
                partial |= interface_type == 0 and vlan_type != 0
        interface_ids = row.get("interfaceIds")
        if interface_ids is None:
            interface_associations["rows_missing"] += 1
            partial = True
        elif (not isinstance(interface_ids, list) or len(interface_ids) > 1024 or
              any(not isinstance(value, str) or len(value) > 512 for value in interface_ids)):
            raise SiteLanNetworkInterfaceSummaryError("field_invalid")
        else:
            interface_associations["identifier_count"] += len(interface_ids)
        subnet = row.get("gatewaySubnet")
        subnet_presence["present" if subnet else "missing"] += 1

        app = row.get("application")
        if app is None:
            applications["unknown"] += 1
            partial = True
        elif type(app) is not int:
            raise SiteLanNetworkInterfaceSummaryError("field_invalid")
        else:
            applications[{0: "gateway_and_switch", 1: "switch_only"}.get(
                app, "unknown")] += 1
            partial |= app not in (0, 1)
    return {
        "network_count": len(rows), "purpose_counts": purposes,
        "interface_vlan_type_counts": vlan_types,
        "application_scope_counts": applications,
        "interface_association_counts": interface_associations,
        "gateway_subnet_presence": subnet_presence,
        "field_presence": field_presence,
        "interface_type_filter": ("single_only" if interface_type == 0 else "all_types"),
        "partial": partial,
        "network_names_ids_vlan_values_and_addresses_returned": False,
        "router_or_vlan_mapping_inferred_from_interface_ids": False,
    }
