"""Compact, identity-free aggregation for global gateway WAN status rows."""
from __future__ import annotations

import math
from typing import Any


class ControllerGatewayWanStatusSummaryError(ValueError):
    """Raised when the paged gateway WAN response exceeds source bounds."""


_ROOT_FIELDS = {"totalRows", "currentPage", "currentSize", "data"}
_GATEWAY_FIELDS = {"siteId", "deviceMac", "uptime", "wanStatus"}
_WAN_FIELDS = {
    "port", "name", "type", "physicalType", "mode", "status", "internetState",
    "ip", "onlineDetection", "ip2", "speed", "duplex", "rx", "rxPkt",
    "rxPktRate", "rxRate", "tx", "txPkt", "txPktRate", "txRate", "proto",
    "healthLevel", "latency", "loss", "rxErrorPkts", "txErrorPkts",
}
_WAN_STRING_FIELDS = {"name", "ip", "ip2", "proto"}
_WAN_INT32_FIELDS = {"port", "type", "physicalType", "mode", "status", "internetState",
                     "onlineDetection", "speed", "duplex", "healthLevel", "latency"}
_WAN_INT64_FIELDS = {"rx", "rxPkt", "rxPktRate", "rxRate", "tx", "txPkt",
                     "txPktRate", "txRate", "rxErrorPkts", "txErrorPkts"}
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1
_MAX_GATEWAYS = 100
_MAX_WAN_PORTS_PER_GATEWAY = 64


def _bounded_int(value: Any, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _enum_count(counts: dict[str, int], field: str, value: int, allowed: set[int]) -> bool:
    if value not in allowed:
        return False
    key = str(value)
    counts[field][key] = counts[field].get(key, 0) + 1
    return True


def project_controller_gateway_wan_status_summary(
    result: Any, *, requested_page_size: int,
) -> dict[str, object]:
    if (not isinstance(result, dict) or len(result) > 8 or
            type(requested_page_size) is not int or not 1 <= requested_page_size <= _MAX_GATEWAYS):
        raise ControllerGatewayWanStatusSummaryError("gateway_page_invalid")
    rows = result.get("data")
    if not isinstance(rows, list) or len(rows) > min(requested_page_size, _MAX_GATEWAYS):
        raise ControllerGatewayWanStatusSummaryError("gateway_rows_invalid")

    missing = invalid = unknown = wan_count = 0
    counts: dict[str, dict[str, int]] = {
        "physical_link_status_counts": {},
        "internet_state_counts": {},
        "online_detection_counts": {},
        "health_level_counts": {},
    }
    numeric_totals = {"rxRate": 0, "txRate": 0, "rxErrorPkts": 0, "txErrorPkts": 0}
    numeric_complete = set(numeric_totals)
    latency_total = loss_total = 0.0
    latency_count = loss_count = 0

    for gateway in rows:
        if not isinstance(gateway, dict) or len(gateway) > 8:
            invalid += 1
            continue
        unknown += len(set(gateway) - _GATEWAY_FIELDS)
        for key in ("siteId", "deviceMac", "uptime"):
            if key in gateway and not isinstance(gateway[key], str):
                invalid += 1
        ports = gateway.get("wanStatus")
        if "wanStatus" not in gateway:
            missing += 1
            continue
        if not isinstance(ports, list) or len(ports) > _MAX_WAN_PORTS_PER_GATEWAY:
            invalid += 1
            continue
        wan_count += len(ports)
        for port in ports:
            if not isinstance(port, dict) or len(port) > 40:
                invalid += 1
                continue
            unknown += len(set(port) - _WAN_FIELDS)
            for key in _WAN_STRING_FIELDS:
                if key in port and not isinstance(port[key], str):
                    invalid += 1
            for key in _WAN_INT32_FIELDS:
                if key not in port:
                    if key in {"status", "internetState", "onlineDetection", "healthLevel"}:
                        missing += 1
                    continue
                if not _bounded_int(port[key], _INT32_MAX):
                    invalid += 1
                    continue
                enum_map = {
                    "status": ("physical_link_status_counts", {0, 1}),
                    "internetState": ("internet_state_counts", {0, 1}),
                    "onlineDetection": ("online_detection_counts", {0, 1}),
                    "healthLevel": ("health_level_counts", set(range(7))),
                }
                if key in enum_map:
                    group, allowed = enum_map[key]
                    if not _enum_count(counts, group, port[key], allowed):
                        invalid += 1
                elif key == "latency":
                    latency_total += port[key]
                    latency_count += 1
            for key in _WAN_INT64_FIELDS:
                if key not in port:
                    if key in numeric_totals:
                        numeric_complete.discard(key)
                        missing += 1
                    continue
                if not _bounded_int(port[key], _INT64_MAX):
                    invalid += 1
                    numeric_complete.discard(key)
                elif key in numeric_totals:
                    numeric_totals[key] += port[key]
            if "loss" in port:
                value = port["loss"]
                if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                        not math.isfinite(value) or not 0 <= value <= 100):
                    invalid += 1
                else:
                    loss_total += float(value)
                    loss_count += 1

    page_fields: dict[str, int | None] = {}
    for source, public, maximum in (
            ("totalRows", "total_gateway_rows", _INT64_MAX),
            ("currentPage", "current_page", _INT32_MAX),
            ("currentSize", "current_page_size", _INT32_MAX)):
        value = result.get(source)
        if source not in result:
            missing += 1
            page_fields[public] = None
        elif _bounded_int(value, maximum):
            page_fields[public] = value
        else:
            invalid += 1
            page_fields[public] = None

    total = page_fields["total_gateway_rows"]
    current = page_fields["current_page"]
    page_size = page_fields["current_page_size"]
    has_more = (current * page_size < total
                if type(current) is int and type(total) is int and
                type(page_size) is int and page_size > 0 else None)
    data: dict[str, object] = {
        "gateway_count": len(rows),
        "wan_port_count": wan_count,
        **page_fields,
        "has_more_pages": has_more,
        **counts,
        "latency_sample_count": latency_count,
        "average_latency_ms": latency_total / latency_count if latency_count else None,
        "packet_loss_sample_count": loss_count,
        "average_packet_loss_percent": loss_total / loss_count if loss_count else None,
        "rx_rate_kilobytes_per_second_total": numeric_totals["rxRate"]
        if "rxRate" in numeric_complete else None,
        "tx_rate_kilobytes_per_second_total": numeric_totals["txRate"]
        if "txRate" in numeric_complete else None,
        "rx_error_packet_total": numeric_totals["rxErrorPkts"]
        if "rxErrorPkts" in numeric_complete else None,
        "tx_error_packet_total": numeric_totals["txErrorPkts"]
        if "txErrorPkts" in numeric_complete else None,
    }
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
