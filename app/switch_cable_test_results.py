"""Bounded projection of previously stored switch cable-test results."""
from __future__ import annotations


class SwitchCableTestResultsError(ValueError):
    """Input exceeds the documented, bounded result projection."""


_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_INT64_MAX = 2**63 - 1
_STATE_CODES = set(range(7))
_MAX_PORTS = 256
_MAX_VALUES_PER_PORT = 16


def _int32(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def project_switch_cable_test_results(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 16:
        raise SwitchCableTestResultsError()
    if any(not isinstance(key, str) or len(key) > 128 for key in raw):
        raise SwitchCableTestResultsError()
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0
    data: dict[str, object] = {}
    status = raw.get("status")
    if "status" not in raw:
        missing.append("status")
        omitted_count += 1
    elif _int32(status):
        data["status_code"] = status
    else:
        omitted.add("status")
        omitted_count += 1

    rows = raw.get("data")
    if "data" not in raw:
        missing.append("data")
        omitted_count += 1
    elif not isinstance(rows, list):
        omitted.add("data")
        omitted_count += 1
    else:
        if len(rows) > _MAX_PORTS:
            raise SwitchCableTestResultsError()
        results: list[dict[str, object]] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or len(row) > 16:
                omitted.add("invalid_ports")
                omitted_count += 1
                continue
            if any(not isinstance(key, str) or len(key) > 128 for key in row):
                raise SwitchCableTestResultsError()
            projected: dict[str, object] = {}
            for field in ("port", "timeStamp"):
                path = f"data[{index}].{field}"
                if field not in row:
                    missing.append(path)
                    omitted_count += 1
                    continue
                value = row[field]
                valid = (_int32(value) if field == "port" else
                         type(value) is int and 0 <= value <= _INT64_MAX)
                if valid:
                    projected["port" if field == "port" else "timestamp_value"] = value
                else:
                    omitted.add(path)
                    omitted_count += 1
            for field in ("state", "length"):
                path = f"data[{index}].{field}"
                if field not in row:
                    missing.append(path)
                    omitted_count += 1
                    continue
                values = row[field]
                if not isinstance(values, list):
                    omitted.add(path)
                    omitted_count += 1
                    continue
                if len(values) > _MAX_VALUES_PER_PORT:
                    raise SwitchCableTestResultsError()
                kept: list[int] = []
                for value_index, value in enumerate(values):
                    valid = (_int32(value) and
                             (field != "state" or value in _STATE_CODES))
                    if valid:
                        kept.append(value)
                    else:
                        omitted.add(f"{path}[{value_index}]")
                        omitted_count += 1
                projected["state_codes" if field == "state" else "length_values"] = kept
            extras = sum(key not in {"port", "standardPort", "state", "length", "timeStamp"}
                         for key in row)
            if extras:
                omitted.add("unknown_fields")
                omitted_count += extras
            if "standardPort" in row:
                omitted.add("port_location_details")
                omitted_count += 1
            results.append(projected)
        data["ports"] = results

    extras = sum(key not in {"status", "data", "stackData"} for key in raw)
    if extras:
        omitted.add("unknown_fields")
        omitted_count += extras
    if "stackData" in raw:
        # Stack member MACs and units are outside this switch-bound projection.
        omitted.add("stack_data")
        omitted_count += 1
    return {"status": "ok", "resource": "switch_cable_test_full_results",
            "data": data, "partial": bool(missing or omitted_count),
            "missing_fields": missing, "omitted_field_count": omitted_count,
            "omitted_fields": sorted(omitted)}
