"""Bounded, redacted projection of TP-Link gateway WAN detail values."""
from __future__ import annotations

import math
from typing import Any


class WanHealthProjectionError(ValueError):
    """The WAN detail response does not match its documented value shapes."""


MAX_WAN_PORTS = 32
INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


def _integer(value: Any, *, bits: int) -> int:
    low, high = (INT32_MIN, INT32_MAX) if bits == 32 else (INT64_MIN, INT64_MAX)
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise WanHealthProjectionError("response_invalid")
    return value


def _number(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WanHealthProjectionError("response_invalid")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        raise WanHealthProjectionError("response_invalid") from None
    if not finite:
        raise WanHealthProjectionError("response_invalid")
    return value


def _project_port(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WanHealthProjectionError("response_invalid")
    out: dict[str, Any] = {}
    for source, target in (("port", "port"), ("proto", "protocol_code"),
                           ("speed", "speed_code"), ("duplex", "duplex_code"),
                           ("latency", "latency")):
        if source in value:
            out[target] = _integer(value[source], bits=32)
    for source, target in (("rx", "rx"), ("tx", "tx"),
                           ("rxRate", "rx_rate"), ("txRate", "tx_rate")):
        if source in value:
            out[target] = _integer(value[source], bits=64)
    if "loss" in value:
        out["loss"] = _number(value["loss"])

    kept = {"port", "proto", "speed", "duplex", "latency", "rx", "tx",
            "rxRate", "txRate", "loss"}
    out["omitted_field_count"] = sum(1 for key in value if key not in kept)
    return out


def project_wan_details(result: Any) -> dict[str, Any]:
    """Project ``WanDetails`` without exposing names, IPs, or identifiers.

    Numeric codes and measurements stay as documented numbers; this function
    assigns no units or enum meanings. Missing ``wanDetails`` is reported as
    incomplete. Port arrays are capped and truncation is reported explicitly.
    """
    # Hardware Controller 6.3 returns the WAN rows directly, while the
    # ER7212PC export wraps them in ``wanDetails``.
    if isinstance(result, list):
        rows = result
        omitted_top_fields = 0
    elif isinstance(result, dict):
        if "wanDetails" not in result:
            return {"wan_details": [], "count": 0, "partial": True,
                    "missing_fields": ["wanDetails"], "omitted_field_count": 0}
        rows = result["wanDetails"]
        omitted_top_fields = sum(1 for key in result if key != "wanDetails")
    else:
        raise WanHealthProjectionError("response_invalid")
    if not isinstance(rows, list):
        raise WanHealthProjectionError("response_invalid")

    projected = [_project_port(row) for row in rows[:MAX_WAN_PORTS]]
    omitted_ports = max(0, len(rows) - MAX_WAN_PORTS)
    partial = omitted_ports > 0 or omitted_top_fields > 0 or any(
        row["omitted_field_count"] > 0 for row in projected
    )
    output: dict[str, Any] = {
        "wan_details": projected,
        "count": len(rows),
        "partial": partial,
        "omitted_field_count": omitted_top_fields,
    }
    if omitted_ports:
        output["omitted_wan_detail_count"] = omitted_ports
    return output
