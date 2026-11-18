"""Redacted summary of networks and devices eligible for DHCP reservations."""

from __future__ import annotations

from collections.abc import Mapping


class SiteNetworkReservationError(ValueError):
    """The controller returned an invalid network-reservation response."""


_NETWORK_FIELDS = frozenset(("id", "name", "type", "serverDevices"))
_SERVER_FIELDS = frozenset((
    "name", "mac", "stackId", "model", "modelVersion", "type", "ranges",
    "configRanges", "dhcpServerEnable", "dhcpSettingsAuto", "supportDhcpReservation",
))


def project_site_network_reservations(result: object) -> dict[str, object]:
    """Aggregate DHCP eligibility and range counts without returning network/device data."""
    if not isinstance(result, Mapping) or len(result) > 16:
        raise SiteNetworkReservationError("result must be a bounded object")
    missing = invalid = unknown = device_count = range_count = network_count = 0
    dhcp_enabled = auto_enabled = reservation_supported = 0
    bool_complete = {"dhcpServerEnable": True, "dhcpSettingsAuto": True,
                     "supportDhcpReservation": True}
    ranges_complete = True
    unknown += sum(key != "networks" for key in result)
    networks = result.get("networks")
    if "networks" not in result:
        missing += 1
        networks = []
    elif not isinstance(networks, list) or len(networks) > 256:
        invalid += 1
        networks = []

    for network in networks:
        if not isinstance(network, Mapping) or len(network) > 16:
            invalid += 1
            continue
        unknown += sum(key not in _NETWORK_FIELDS for key in network)
        for key in ("id", "name", "type"):
            if key in network and not isinstance(network[key], str):
                invalid += 1
        devices = network.get("serverDevices")
        if "serverDevices" not in network:
            missing += 1
            continue
        if not isinstance(devices, list) or len(devices) > 256:
            invalid += 1
            continue
        network_count += 1
        for server in devices:
            if not isinstance(server, Mapping) or len(server) > 32:
                invalid += 1
                continue
            device_count += 1
            unknown += sum(key not in _SERVER_FIELDS for key in server)
            for key in ("name", "mac", "stackId", "model", "modelVersion", "type"):
                if key in server and not isinstance(server[key], str):
                    invalid += 1
            for key, target in (("dhcpServerEnable", "dhcp"),
                                ("dhcpSettingsAuto", "auto"),
                                ("supportDhcpReservation", "reservation")):
                value = server.get(key)
                if key not in server:
                    missing += 1
                    bool_complete[key] = False
                elif not isinstance(value, bool):
                    invalid += 1
                    bool_complete[key] = False
                elif target == "dhcp":
                    dhcp_enabled += int(value)
                elif target == "auto":
                    auto_enabled += int(value)
                else:
                    reservation_supported += int(value)
            ranges = server.get("ranges")
            if "ranges" not in server:
                missing += 1
                ranges_complete = False
            elif not isinstance(ranges, list) or len(ranges) > 4096:
                invalid += 1
                ranges_complete = False
            else:
                for item in ranges:
                    if not isinstance(item, Mapping) or len(item) > 8:
                        invalid += 1
                        ranges_complete = False
                        continue
                    unknown += sum(key not in ("ipaddrStart", "ipaddrEnd") for key in item)
                    for key in ("ipaddrStart", "ipaddrEnd"):
                        if key in item and not isinstance(item[key], str):
                            invalid += 1
                            ranges_complete = False
                    range_count += 1

    return {
        "data": {
            "eligible_network_count": network_count,
            "dhcp_server_count": device_count,
            "dhcp_enabled_server_count": dhcp_enabled if bool_complete["dhcpServerEnable"] else None,
            "auto_configured_server_count": auto_enabled if bool_complete["dhcpSettingsAuto"] else None,
            "reservation_supported_server_count": (
                reservation_supported if bool_complete["supportDhcpReservation"] else None),
            "configured_range_count": range_count if ranges_complete else None,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
