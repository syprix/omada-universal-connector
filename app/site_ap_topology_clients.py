"""Redacted counts from the topology client list of one selected AP."""
from __future__ import annotations

from collections.abc import Mapping


class SiteApTopologyClientsError(ValueError):
    pass


def project_site_ap_topology_clients(rows: object) -> dict[str, object]:
    if not isinstance(rows, list) or len(rows) > 4_096:
        raise SiteApTopologyClientsError("rows_invalid")
    wireless = wired = connection_unknown = type_present = type_missing = 0
    guest = non_guest = guest_unknown = 0
    partial = False
    known = {"mac", "name", "wireless", "uplinkSwitchInfo", "uplinkApInfo",
             "uplinkGatewayInfo", "guest", "type"}
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 32:
            raise SiteApTopologyClientsError("row_invalid")
        if set(row) - known:
            partial = True
        for field in ("mac", "name"):
            if field in row and (not isinstance(row[field], str) or len(row[field]) > 512):
                raise SiteApTopologyClientsError("identity_invalid")
        for field in ("uplinkSwitchInfo", "uplinkApInfo", "uplinkGatewayInfo"):
            if field in row and (not isinstance(row[field], Mapping) or len(row[field]) > 32):
                raise SiteApTopologyClientsError("uplink_invalid")
        if "type" in row:
            if not isinstance(row["type"], str) or len(row["type"]) > 256:
                raise SiteApTopologyClientsError("type_invalid")
            type_present += 1
        else:
            type_missing += 1
            partial = True
        if "wireless" not in row:
            connection_unknown += 1
            partial = True
        elif type(row["wireless"]) is not bool:
            raise SiteApTopologyClientsError("wireless_invalid")
        elif row["wireless"]:
            wireless += 1
        else:
            wired += 1
        if "guest" not in row:
            guest_unknown += 1
        elif type(row["guest"]) is not bool:
            raise SiteApTopologyClientsError("guest_invalid")
        elif row["guest"]:
            guest += 1
        else:
            non_guest += 1
    return {
        "topology_client_count": len(rows),
        "by_connection": {"wireless": wireless, "wired": wired,
                          "unknown": connection_unknown},
        "type_present_count": type_present,
        "type_missing_count": type_missing,
        "by_guest_flag": {"guest": guest, "non_guest": non_guest,
                           "unknown": guest_unknown},
        "partial": partial,
        "source_view": "topology_snapshot",
        "source_timestamp_provided": False,
        "roaming_history_included": False,
        "client_identities_returned": False,
    }
