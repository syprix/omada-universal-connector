"""Counts for documented controller-reported optical DDM flags."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_ROWS = 1_000
FIELDS = ("dataReady", "transmitFault", "lossOfSignal")


def summarize_switch_ddm_rows(rows: object) -> dict[str, Any]:
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError("input_invalid")
    counts = {
        "dataReady": {"valid": 0, "invalid": 0, "missing": 0, "unknown": 0},
        "transmitFault": {"reported_clear": 0, "reported_fault": 0,
                          "missing": 0, "invalid": 0},
        "lossOfSignal": {"reported_clear": 0, "reported_loss": 0,
                         "missing": 0, "invalid": 0},
    }
    allowed = {"port", "standardPort", "rxPower", "rxPowerDbm", "biasCurrent",
               "dataReady", "voltage", "transmitFault", "txPower", "txPowerDbm",
               "lossOfSignal", "temperature", "temperatureFah"}
    invalid_rows = unknown_fields = 0
    partial = False
    for row in rows:
        if not isinstance(row, Mapping):
            invalid_rows += 1
            for field in FIELDS:
                counts[field]["unknown" if field == "dataReady" else "invalid"] += 1
            partial = True
            continue
        unknown_fields += sum(field not in allowed for field in row)
        ready = row.get("dataReady")
        if type(ready) is int and ready in (0, 1):
            counts["dataReady"]["valid" if ready == 1 else "invalid"] += 1
        elif "dataReady" not in row:
            counts["dataReady"]["missing"] += 1
        else:
            counts["dataReady"]["unknown"] += 1
        for field, clear_label, asserted_label in (
                ("transmitFault", "reported_clear", "reported_fault"),
                ("lossOfSignal", "reported_clear", "reported_loss")):
            value = row.get(field)
            if type(value) is int and value in (0, 1):
                counts[field][asserted_label if value == 1 else clear_label] += 1
            elif field not in row:
                counts[field]["missing"] += 1
            else:
                counts[field]["invalid"] += 1
    partial = partial or bool(invalid_rows or unknown_fields or any(
        value for field in FIELDS for key, value in counts[field].items()
        if key in ("missing", "unknown", "invalid")))
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_switch_ddm_summary",
        "reported_optical_module_count": len(rows),
        "reported_controller_flags": counts,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "port_numbers_and_optical_measurements_returned": False,
        "device_health_inferred": False,
    }
