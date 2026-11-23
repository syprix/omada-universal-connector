"""Safe S2S VPN inventory and peer status summaries."""
from __future__ import annotations

from collections.abc import Mapping


class SiteS2SVpnError(ValueError):
    pass


_VPN_FIELDS = frozenset(("id", "name", "siteVpnType", "status", "remoteSite",
                         "remoteIp", "remoteSubnet", "networkType", "networkList",
                         "customNetwork", "preSharedKey", "wan", "advancedSetting"))


def project_s2s_vpn_inventory(rows: object, refs: list[str | None], *, max_items: int = 10_000
                              ) -> dict[str, object]:
    if (not isinstance(rows, list) or len(rows) > max_items or len(refs) != len(rows)):
        raise SiteS2SVpnError("invalid VPN inventory")
    type_counts = {"auto_ipsec": 0, "manual_ipsec": 0, "unknown": 0}
    invalid = unknown = missing_id = 0
    items: list[dict[str, object]] = []
    for row, ref in zip(rows, refs):
        if not isinstance(row, Mapping) or len(row) > 32:
            invalid += 1
            type_counts["unknown"] += 1
            continue
        unknown += sum(key not in _VPN_FIELDS for key in row)
        raw_type = row.get("siteVpnType")
        if type(raw_type) is int and raw_type in (0, 1):
            type_counts["auto_ipsec" if raw_type == 0 else "manual_ipsec"] += 1
            vpn_type: int | None = raw_type
        else:
            type_counts["unknown"] += 1
            vpn_type = None
        raw_id = row.get("id")
        if not isinstance(raw_id, str) or not raw_id or not ref:
            missing_id += 1
            continue
        item: dict[str, object] = {"vpn_ref": ref}
        if vpn_type is not None:
            item["site_vpn_type"] = vpn_type
        items.append(item)
    return {
        "status": "ok", "resource": "site_s2s_vpn_inventory_summary",
        "reported_vpn_count": len(rows), "returned_vpn_count": len(items),
        "vpn_type_counts": type_counts, "unbound_vpn_count": missing_id + invalid,
        "unknown_field_count": unknown, "invalid_record_count": invalid,
        "items": items,
        "partial": bool(invalid or missing_id or unknown or type_counts["unknown"]),
    }


def project_s2s_peer_status(rows: object, reported_total: int, pages_fetched: int,
                            page_limit: int, *, support_wireguard_status: object = None
                            ) -> dict[str, object]:
    if (not isinstance(rows, list) or len(rows) > 10_000 or type(reported_total) is not int or
            reported_total < 0 or type(pages_fetched) is not int or pages_fetched < 0 or
            type(page_limit) is not int or page_limit < 1):
        raise SiteS2SVpnError("invalid peer list")
    counts = {"connected": 0, "disconnected": 0, "unknown": 0}
    invalid = unknown_fields = status_missing = 0
    allowed = {"id", "vpnId", "name", "remoteIp", "localIp", "downPkts", "downBytes",
               "upPkts", "upBytes", "loginTime", "port", "status"}
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 24:
            invalid += 1
            counts["unknown"] += 1
            continue
        unknown_fields += sum(key not in allowed for key in row)
        status = row.get("status")
        if type(status) is int and status == 1:
            counts["connected"] += 1
        elif type(status) is int and status == 0:
            counts["disconnected"] += 1
        elif status is None:
            counts["unknown"] += 1
            status_missing += 1
        else:
            counts["unknown"] += 1
            invalid += 1
    wireguard_reported = type(support_wireguard_status) is bool
    return {
        "status": "ok", "resource": "site_s2s_peer_status_summary",
        "reported_peer_count": reported_total, "returned_peer_count": len(rows),
        "peer_status_counts": counts, "status_semantics": {
            "0": "disconnected", "1": "connected", "other": "unknown"},
        "support_wireguard_status_reported": wireguard_reported,
        "pages_fetched": pages_fetched, "page_limit": page_limit,
        "truncated": len(rows) < reported_total,
        "invalid_record_count": invalid, "missing_status_count": status_missing,
        "unknown_field_count": unknown_fields,
        "partial": bool(len(rows) < reported_total or invalid or status_missing or
                         unknown_fields or not wireguard_reported),
    }
