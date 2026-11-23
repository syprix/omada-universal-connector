"""Redacted counts for deprecated IPsec failover configuration rows."""
from __future__ import annotations
from collections.abc import Mapping


class IpsecFailoverSummaryError(ValueError):
    pass


def _validate_reference(value: object) -> None:
    if not isinstance(value, Mapping) or set(value) - {"id", "name", "status"}:
        raise IpsecFailoverSummaryError("reference_invalid")
    for key in ("id", "name"):
        field = value.get(key)
        if field is not None and (not isinstance(field, str) or len(field) > 512):
            raise IpsecFailoverSummaryError("reference_invalid")
    status = value.get("status")
    if status is not None and (type(status) is not int or not -(2**31) <= status < 2**31):
        raise IpsecFailoverSummaryError("reference_invalid")


def project_ipsec_failover_page(payload: object, expected_page: int,
                                page_size: int, max_rows: int) -> dict[str, object]:
    if (not isinstance(payload, Mapping) or set(payload) - {"errorCode", "msg", "result"} or
            type(payload.get("errorCode")) is not int or
            not -(2**31) <= payload.get("errorCode") < 2**31 or payload.get("errorCode") != 0 or
            (payload.get("msg") is not None and
             (not isinstance(payload.get("msg"), str) or len(payload["msg"]) > 4_096))):
        raise IpsecFailoverSummaryError("envelope_invalid")
    grid = payload.get("result")
    if not isinstance(grid, Mapping) or set(grid) - {"totalRows", "currentPage", "currentSize", "data"}:
        raise IpsecFailoverSummaryError("grid_invalid")
    total, page, size, rows = (grid.get(key) for key in
                               ("totalRows", "currentPage", "currentSize", "data"))
    if (type(total) is not int or not 0 <= total < (1 << 63) or
            type(page) is not int or page != expected_page or
            type(size) is not int or not 0 <= size <= page_size or
            not isinstance(rows, list) or len(rows) > page_size or size not in (len(rows), page_size)):
        raise IpsecFailoverSummaryError("grid_invalid")

    selected = rows[:max(0, max_rows)]
    primary_count = primary_unknown = candidate_count = candidate_unknown = 0
    failback_enabled = failback_disabled = failback_unknown = 0
    failback_time_present = 0
    for row in selected:
        if not isinstance(row, Mapping) or set(row) - {
                "id", "name", "primary", "candidates", "failBack", "failBackTime"}:
            raise IpsecFailoverSummaryError("row_invalid")
        for key in ("id", "name"):
            value = row.get(key)
            if value is not None and (not isinstance(value, str) or len(value) > 512):
                raise IpsecFailoverSummaryError("row_invalid")
        primary = row.get("primary")
        if isinstance(primary, Mapping):
            _validate_reference(primary)
            primary_count += 1
        else:
            if primary is not None:
                raise IpsecFailoverSummaryError("row_invalid")
            primary_unknown += 1
        candidates = row.get("candidates")
        if isinstance(candidates, list) and len(candidates) <= 1_000:
            for candidate in candidates:
                _validate_reference(candidate)
            candidate_count += len(candidates)
        elif candidates is None:
            candidate_unknown += 1
        else:
            raise IpsecFailoverSummaryError("row_invalid")
        failback = row.get("failBack")
        if type(failback) is bool:
            failback_enabled += int(failback)
            failback_disabled += int(not failback)
        elif failback is None:
            failback_unknown += 1
        else:
            raise IpsecFailoverSummaryError("row_invalid")
        failback_time = row.get("failBackTime")
        if failback_time is not None:
            if type(failback_time) is not int or not -(2**31) <= failback_time < 2**31:
                raise IpsecFailoverSummaryError("row_invalid")
            failback_time_present += 1

    return {
        "total_rows": total,
        "rows": len(selected),
        "primary_reference_count": primary_count,
        "primary_reference_unknown_count": primary_unknown,
        "candidate_reference_count": candidate_count,
        "candidate_list_unknown_count": candidate_unknown,
        "failback_enabled_count": failback_enabled,
        "failback_disabled_count": failback_disabled,
        "failback_unknown_count": failback_unknown,
        "failback_time_field_present_count": failback_time_present,
        "failback_time_field_missing_count": len(selected) - failback_time_present,
    }
