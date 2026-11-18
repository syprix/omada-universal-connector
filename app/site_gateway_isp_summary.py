"""Redacted gateway and WAN ISP status and peak utilization totals."""
from __future__ import annotations

import math
from typing import Any


class SiteGatewayIspSummaryError(ValueError):
    """Raised when the documented gateway ISP response exceeds bounds."""


_GATEWAY_STATUS = {-1: "disconnected", 0: "backup", 1: "active"}
_ISP_STATUS = {0: "backup", 1: "primary", 2: "normal"}
_GATEWAY_FIELDS = {"name", "mac", "status", "ispInfo", "speedTestLimit", "supportSpeedTest"}
_ISP_INFO_FIELDS = {"type", "ispArr"}
_ISP_FIELDS = {"port", "name", "portUuid", "maxBandwidth", "downloadSpeedSet",
               "uploadSpeedSet", "downloadSpeed", "uploadSpeed", "downloadPercent",
               "uploadPercent", "ip", "loadBalance", "status", "onLineStatus", "ipv4Proto"}


def _percentage(value: Any) -> float | None:
    try:
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
            return None
        return float(value)
    except (OverflowError, TypeError):
        return None


def project_site_gateway_isp_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 4:
        raise SiteGatewayIspSummaryError("response_invalid")
    rows = result.get("data")
    if not isinstance(rows, list) or len(rows) > 20:
        raise SiteGatewayIspSummaryError("gateway_rows_invalid")
    gateway_counts = {name: 0 for name in _GATEWAY_STATUS.values()}
    isp_counts = {name: 0 for name in _ISP_STATUS.values()}
    online = offline = invalid = unknown = missing = 0
    upload: list[float] = []
    download: list[float] = []
    for gateway in rows:
        if not isinstance(gateway, dict) or len(gateway) > 12:
            invalid += 1
            continue
        unknown += len(set(gateway) - _GATEWAY_FIELDS)
        gateway_status = gateway.get("status")
        if type(gateway_status) is int and gateway_status in _GATEWAY_STATUS:
            gateway_counts[_GATEWAY_STATUS[gateway_status]] += 1
        elif "status" not in gateway:
            missing += 1
        else:
            invalid += 1
        if "ispInfo" not in gateway:
            missing += 1
            continue
        info = gateway["ispInfo"]
        if not isinstance(info, dict) or len(info) > 6:
            invalid += 1
            continue
        unknown += len(set(info) - _ISP_INFO_FIELDS)
        if "ispArr" not in info:
            missing += 1
            continue
        isps = info["ispArr"]
        if not isinstance(isps, list) or len(isps) > 100:
            invalid += 1
            continue
        for isp in isps:
            if not isinstance(isp, dict) or len(isp) > 20:
                invalid += 1
                continue
            unknown += len(set(isp) - _ISP_FIELDS)
            status = isp.get("status")
            if type(status) is int and status in _ISP_STATUS:
                isp_counts[_ISP_STATUS[status]] += 1
            elif "status" not in isp:
                missing += 1
            else:
                invalid += 1
            online_status = isp.get("onLineStatus")
            if type(online_status) is int and online_status in (0, 1):
                online += int(online_status == 1)
                offline += int(online_status == 0)
            elif "onLineStatus" not in isp:
                missing += 1
            else:
                invalid += 1
            for key, target in (("uploadPercent", upload), ("downloadPercent", download)):
                if key in isp:
                    value = _percentage(isp[key])
                    if value is None:
                        invalid += 1
                    else:
                        target.append(value)
                else:
                    missing += 1
    data: dict[str, object] = {
        "gateway_count": len(rows), "gateway_status_counts": gateway_counts,
        "isp_status_counts": isp_counts, "online_isp_count": online,
        "offline_isp_count": offline,
    }
    if upload:
        data["maximum_upload_utilization_percent"] = max(upload)
    if download:
        data["maximum_download_utilization_percent"] = max(download)
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
