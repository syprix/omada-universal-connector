"""Redacted summary of paginated site VPN tunnel sessions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping


class SiteVpnSessionError(ValueError):
    """The controller returned an invalid VPN-session page."""


_PAGE_FIELDS = frozenset(("totalRows", "currentPage", "currentSize", "data"))
_ROW_TYPES = {
    "vpnId": int, "vpnName": str, "userId": int, "userName": str,
    "interfaceName": str, "serverType": int, "vpnType": int, "clientMode": str,
    "localIp": str, "remoteIp": str, "downPkts": int, "downBytes": int,
    "upPkts": int, "upBytes": int, "uptime": str, "dns": str,
}
_BYTE_FIELDS = ("downBytes", "upBytes", "downPkts", "upPkts")
_MAX_I32 = 2_147_483_647
_MAX_I64 = 9_223_372_036_854_775_807
_PAGE_SIZE = 100
_MAX_PAGES = 5


def project_site_vpn_sessions(pages: object) -> dict[str, object]:
    """Aggregate session counts and traffic while omitting all user/network identities."""
    if not isinstance(pages, list) or not 1 <= len(pages) <= _MAX_PAGES:
        raise SiteVpnSessionError("pages must be a bounded non-empty list")
    missing = invalid = unknown = returned = page_count = 0
    total_rows: int | None = None
    vpn_types: Counter[int] = Counter()
    server_types: Counter[int] = Counter()
    totals = {key: 0 for key in _BYTE_FIELDS}
    totals_complete = {key: True for key in _BYTE_FIELDS}

    for index, page in enumerate(pages, start=1):
        if not isinstance(page, Mapping) or len(page) > 16:
            invalid += 1
            continue
        unknown += sum(key not in _PAGE_FIELDS for key in page)
        value = page.get("totalRows")
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= _MAX_I64:
            if "totalRows" not in page:
                missing += 1
            else:
                invalid += 1
            value = None
        elif total_rows is None:
            total_rows = value
        elif total_rows != value:
            invalid += 1

        current_page = page.get("currentPage")
        if not isinstance(current_page, int) or isinstance(current_page, bool) or not 1 <= current_page <= _MAX_I32:
            if "currentPage" not in page:
                missing += 1
            else:
                invalid += 1
        elif current_page != index:
            invalid += 1

        current_size = page.get("currentSize")
        if not isinstance(current_size, int) or isinstance(current_size, bool) or not 0 <= current_size <= _PAGE_SIZE:
            if "currentSize" not in page:
                missing += 1
            else:
                invalid += 1

        rows = page.get("data")
        if not isinstance(rows, list) or len(rows) > _PAGE_SIZE:
            if "data" not in page:
                missing += 1
            else:
                invalid += 1
            continue
        page_count += 1
        returned += len(rows)
        if isinstance(current_size, int) and not isinstance(current_size, bool) and current_size != len(rows):
            invalid += 1
        for row in rows:
            if not isinstance(row, Mapping) or len(row) > 32:
                invalid += 1
                continue
            unknown += sum(key not in _ROW_TYPES for key in row)
            for key, typ in _ROW_TYPES.items():
                if key not in row:
                    if key in _BYTE_FIELDS or key in ("vpnType", "serverType"):
                        missing += 1
                        if key in _BYTE_FIELDS:
                            totals_complete[key] = False
                    continue
                item = row[key]
                if typ is int:
                    maximum = _MAX_I64 if key in _BYTE_FIELDS else _MAX_I32
                    minimum = 0 if key in _BYTE_FIELDS else -(2**31)
                    if (not isinstance(item, int) or isinstance(item, bool) or
                            not minimum <= item <= maximum):
                        invalid += 1
                        if key in _BYTE_FIELDS:
                            totals_complete[key] = False
                        continue
                    if key in _BYTE_FIELDS:
                        totals[key] += item
                    elif key == "vpnType":
                        vpn_types[item] += 1
                    elif key == "serverType":
                        server_types[item] += 1
                elif not isinstance(item, str):
                    invalid += 1

    truncated = total_rows is None or returned < total_rows
    if total_rows is not None and returned > total_rows:
        invalid += 1
    if total_rows == 0 and returned != 0:
        invalid += 1
    return {
        "data": {
            "reported_session_count": total_rows,
            "returned_session_count": returned,
            "vpn_type_code_counts": {str(k): v for k, v in sorted(vpn_types.items())},
            "server_type_code_counts": {str(k): v for k, v in sorted(server_types.items())},
            "downstream_bytes": totals["downBytes"] if totals_complete["downBytes"] else None,
            "upstream_bytes": totals["upBytes"] if totals_complete["upBytes"] else None,
            "downstream_packets": totals["downPkts"] if totals_complete["downPkts"] else None,
            "upstream_packets": totals["upPkts"] if totals_complete["upPkts"] else None,
            "pages_read": page_count,
            "truncated": truncated,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or truncated),
    }
