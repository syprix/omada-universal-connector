"""Redacted projections for the documented site-to-site VPN status list."""
from __future__ import annotations

from collections.abc import Mapping


class SiteVpnS2SStatusError(ValueError):
    pass


def project_site_vpn_s2s_status(rows: object, vpn_type: int,
                                total_count: int, pages_fetched: int,
                                page_limit: int,
                                support_wireguard_status: object = None) -> dict[str, object]:
    if (type(vpn_type) is not int or vpn_type not in {2, 4} or
            not isinstance(rows, list) or len(rows) > 1_000 or
            type(total_count) is not int or total_count < len(rows) or
            type(pages_fetched) is not int or pages_fetched < 0 or
            type(page_limit) is not int or not 1 <= page_limit <= 10):
        raise SiteVpnS2SStatusError("input_invalid")
    counts: dict[str, int] = {}
    unknown = 0
    partial = len(rows) < total_count
    known = {
        "id": str, "vpnId": str, "spi": int, "name": str, "direction": str,
        "localPeerIp": str, "remotePeerIp": str, "localIp": str, "remoteIp": str,
        "localSa": str, "remoteSa": str, "protocol": str, "ahAuthentication": str,
        "espAuthentication": str, "espEncryption": str, "userId": int, "userName": str,
        "interfaceName": str, "serverType": int, "vpnType": int, "clientMode": int,
        "downPkts": int, "downBytes": int, "upPkts": int, "upBytes": int,
        "uptime": str, "dns": str, "authType": int, "loginTime": int,
        "loginIp": str, "virtualIp": str, "ipPoolType": int, "ipPoolStart": str,
        "ipPoolEnd": str, "ipPool": str, "port": int, "servicePort": int,
        "connectedNum": int, "disconnectedNum": int, "totalRemoteNum": int,
        "status": int,
    }
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 64:
            raise SiteVpnS2SStatusError("row_invalid")
        if set(row) - set(known):
            partial = True
        for field, value in row.items():
            kind = known.get(field)
            if kind is None:
                continue
            if kind is str:
                if not isinstance(value, str) or len(value) > 512:
                    raise SiteVpnS2SStatusError("field_invalid")
            elif (type(value) is not int or
                  (field in {"spi", "downPkts", "downBytes", "upPkts", "upBytes",
                             "loginTime", "connectedNum", "disconnectedNum", "totalRemoteNum"}
                   and not -(1 << 63) <= value < (1 << 63)) or
                  (field not in {"spi", "downPkts", "downBytes", "upPkts", "upBytes",
                                 "loginTime", "connectedNum", "disconnectedNum", "totalRemoteNum"}
                   and not -(1 << 31) <= value < (1 << 31))):
                raise SiteVpnS2SStatusError("field_invalid")
        status = row.get("status")
        if type(status) is not int:
            unknown += 1
            partial = True
        else:
            counts[str(status)] = counts.get(str(status), 0) + 1
    if support_wireguard_status is not None and type(support_wireguard_status) is not bool:
        raise SiteVpnS2SStatusError("field_invalid")
    return {
        "vpn_type": vpn_type,
        "vpn_type_name": "ipsec" if vpn_type == 2 else "wireguard",
        "returned_count": len(rows),
        "total_count": total_count,
        "status_code_counts": dict(sorted(counts.items(), key=lambda item: int(item[0]))),
        "status_unknown_count": unknown,
        "pages_fetched": pages_fetched,
        "page_limit": page_limit,
        "support_wireguard_status": support_wireguard_status,
        "partial": partial,
    }
