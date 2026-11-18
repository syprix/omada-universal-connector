"""Redacted projection of saved gateway WAN speed-test results."""
from __future__ import annotations

import math
from typing import Any


class GatewaySpeedTestError(ValueError):
    """The saved gateway speed-test response cannot be safely projected."""


_INT32 = frozenset({"portId", "virtualWanEntryId", "status", "latency"})
_INT64 = frozenset({"time", "down", "up"})
_REDACTED = frozenset({"portName", "isp", "serverName", "serverLocation"})
_FIELDS = _INT32 | _INT64 | _REDACTED | {"progress"}


def project_gateway_speed_test(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or len(raw) > 16:
        raise GatewaySpeedTestError("response_invalid")
    status = raw.get("status")
    if type(status) is not int or not -(2**31) <= status <= 2**31 - 1:
        raise GatewaySpeedTestError("response_invalid")
    source_rows = raw.get("portSpeedResults")
    if not isinstance(source_rows, list) or len(source_rows) > 64:
        raise GatewaySpeedTestError("response_invalid")
    top_unknown = len(set(raw) - {"status", "portSpeedResults"})
    partial = bool(top_unknown)
    rows: list[dict[str, int | float]] = []
    unknown, redacted, omitted = top_unknown, 0, 0
    for row in source_rows:
        if not isinstance(row, dict) or len(row) > 32:
            raise GatewaySpeedTestError("response_invalid")
        item: dict[str, int | float] = {}
        for field, value in row.items():
            if field in _REDACTED:
                redacted += 1
            elif field not in _FIELDS:
                unknown += 1
                partial = True
            elif field in _INT32:
                if type(value) is int and -(2**31) <= value <= 2**31 - 1:
                    item[field] = value
                else:
                    partial = True
            elif field in _INT64:
                if type(value) is int and 0 <= value <= 2**63 - 1:
                    item[field] = value
                else:
                    partial = True
            elif type(value) in (int, float) and math.isfinite(value):
                item[field] = value
            else:
                partial = True
        if item:
            rows.append(item)
        else:
            omitted += 1
            partial = True
    return {"status": "ok", "resource": "gateway_speed_test_results",
            "data": {"status_code": status, "count": len(rows), "source_count": len(source_rows),
                     "items": rows, "partial": partial, "omitted_count": omitted,
                     "unknown_field_count": unknown, "redacted_field_count": redacted}}
