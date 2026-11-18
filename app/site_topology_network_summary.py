"""Redacted counts from the topology's available network and SSID read."""

from __future__ import annotations

from typing import Any

MAX_ROWS = 256
INT32_MAX = 2**31 - 1


class TopologyNetworkSummaryError(ValueError):
    """The topology network summary is malformed or outside projection bounds."""


def _int32(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= INT32_MAX:
        raise TopologyNetworkSummaryError("response_invalid")
    return value


def _bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise TopologyNetworkSummaryError("response_invalid")
    return value


def project_topology_network_summary(result: Any) -> dict[str, object]:
    """Return bounded counts only; omit IDs, names, VLAN IDs and raw rows."""
    if not isinstance(result, dict):
        raise TopologyNetworkSummaryError("response_invalid")
    known = {"splitNetworks", "ssids"}
    unknown_field_count = sum(1 for key in result if key not in known)
    partial = unknown_field_count > 0
    output: dict[str, object] = {"unknown_field_count": unknown_field_count}

    networks = result.get("splitNetworks")
    unknown_network_fields = 0
    if networks is None:
        output["split_network_count"] = None
        output["default_network_count"] = None
        output["configuring_network_count"] = None
        partial = True
    else:
        if not isinstance(networks, list) or len(networks) > MAX_ROWS:
            raise TopologyNetworkSummaryError("response_invalid")
        default_count = 0
        configuring_count = 0
        default_complete = True
        configuring_complete = True
        for row in networks:
            if not isinstance(row, dict):
                raise TopologyNetworkSummaryError("response_invalid")
            unknown_network_fields += sum(
                1 for key in row
                if key not in {"id", "name", "vlanId", "defaultNetwork", "configuring"}
            )
            if "vlanId" not in row:
                partial = True
            else:
                _int32(row["vlanId"])
            for field in ("defaultNetwork", "configuring"):
                if field in row:
                    value = _bool(row[field])
                    if field == "defaultNetwork":
                        default_count += int(value)
                    else:
                        configuring_count += int(value)
                else:
                    if field == "defaultNetwork":
                        default_complete = False
                    else:
                        configuring_complete = False
                    partial = True
        output["split_network_count"] = len(networks)
        output["default_network_count"] = default_count if default_complete else None
        output["configuring_network_count"] = configuring_count if configuring_complete else None
    output["unknown_network_field_count"] = unknown_network_fields
    partial = partial or unknown_network_fields > 0

    ssids = result.get("ssids")
    unknown_ssid_fields = 0
    if ssids is None:
        output.update({"ssid_count": None, "ssid_vlan_enabled_count": None,
                       "ssid_configuring_count": None, "ssid_client_count_sum": None,
                       "ssid_vlan_id_count": None})
        partial = True
    else:
        if not isinstance(ssids, list) or len(ssids) > MAX_ROWS:
            raise TopologyNetworkSummaryError("response_invalid")
        vlan_enabled_count = 0
        configuring_count = 0
        client_count_sum = 0
        vlan_id_count = 0
        vlan_enabled_complete = True
        configuring_complete = True
        client_count_complete = True
        vlan_ids_complete = True
        for row in ssids:
            if not isinstance(row, dict):
                raise TopologyNetworkSummaryError("response_invalid")
            unknown_ssid_fields += sum(
                1 for key in row
                if key not in {"id", "name", "wlanName", "vlanEnable", "vlanIds",
                               "configuring", "clientNum"}
            )
            if "vlanEnable" in row:
                vlan_enabled_count += int(_bool(row["vlanEnable"]))
            else:
                vlan_enabled_complete = False
                partial = True
            if "configuring" in row:
                configuring_count += int(_bool(row["configuring"]))
            else:
                configuring_complete = False
                partial = True
            if "clientNum" in row:
                client_count_sum += _int32(row["clientNum"])
                if client_count_sum > INT32_MAX:
                    raise TopologyNetworkSummaryError("response_invalid")
            else:
                client_count_complete = False
                partial = True
            if "vlanIds" in row:
                values = row["vlanIds"]
                if not isinstance(values, list) or len(values) > MAX_ROWS:
                    raise TopologyNetworkSummaryError("response_invalid")
                for value in values:
                    _int32(value)
                vlan_id_count += len(values)
                if vlan_id_count > MAX_ROWS * MAX_ROWS:
                    raise TopologyNetworkSummaryError("response_invalid")
            else:
                vlan_ids_complete = False
                partial = True
        output["ssid_count"] = len(ssids)
        output["ssid_vlan_enabled_count"] = vlan_enabled_count if vlan_enabled_complete else None
        output["ssid_configuring_count"] = configuring_count if configuring_complete else None
        output["ssid_client_count_sum"] = client_count_sum if client_count_complete else None
        output["ssid_vlan_id_count"] = vlan_id_count if vlan_ids_complete else None
    output["unknown_ssid_field_count"] = unknown_ssid_fields
    partial = partial or unknown_ssid_fields > 0

    output["partial"] = partial
    return output
