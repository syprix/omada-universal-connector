"""Redacted firmware-log selectors and failed-device counts."""
from __future__ import annotations
from collections.abc import Callable, Mapping
import re


class UpgradeFailureSummaryError(ValueError):
    pass


_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}")


def _grid(result: object, expected_page: int, page_size: int) -> tuple[int, list[object]]:
    if not isinstance(result, Mapping) or set(result) - {"totalRows", "currentPage", "currentSize", "data"}:
        raise UpgradeFailureSummaryError("grid_invalid")
    total, page, size, rows = (result.get(k) for k in
                               ("totalRows", "currentPage", "currentSize", "data"))
    if (type(total) is not int or not 0 <= total < (1 << 63) or
            type(page) is not int or page != expected_page or
            type(size) is not int or not 0 <= size <= page_size or
            not isinstance(rows, list) or len(rows) > page_size or
            size not in (len(rows), page_size) or len(rows) > total):
        raise UpgradeFailureSummaryError("grid_invalid")
    return total, rows


def validate_operation_envelope(payload: object) -> Mapping[str, object]:
    if (not isinstance(payload, Mapping) or set(payload) - {"errorCode", "msg", "result"} or
            type(payload.get("errorCode")) is not int or
            not -(2**31) <= payload.get("errorCode") < 2**31 or payload.get("errorCode") != 0 or
            (payload.get("msg") is not None and
             (not isinstance(payload.get("msg"), str) or len(payload["msg"]) > 4_096)) or
            not isinstance(payload.get("result"), Mapping)):
        raise UpgradeFailureSummaryError("envelope_invalid")
    return payload["result"]


def project_upgrade_log_inventory_page(
        result: object, expected_page: int, page_size: int,
        make_ref: Callable[[str], str]) -> dict[str, object]:
    if (isinstance(result, Mapping) and type(result.get("totalRows")) is int and
            result.get("totalRows") == 0 and type(result.get("currentPage")) is int and
            result.get("currentPage") == 0 and type(result.get("currentSize")) is int and
            result.get("currentSize") == 0 and
            result.get("data") == [{"id": "", "modelTypeInfo":
                {"showModel": "", "compoundModel": ""}, "siteNames": [], "siteNum": 0,
                "currentVersion": [], "targetVersion": "", "upgradeTime": "",
                "operator": "", "rollbacked": True, "failedDeviceNum": 0}]):
        total, rows = 0, []
    else:
        total, rows = _grid(result, expected_page, page_size)
    ids: dict[str, int] = {}
    missing = 0
    for row in rows:
        if not isinstance(row, Mapping):
            raise UpgradeFailureSummaryError("row_invalid")
        raw_id = row.get("id")
        if not isinstance(raw_id, str) or not _IDENTIFIER.fullmatch(raw_id):
            missing += 1
            continue
        ref = make_ref(raw_id)
        ids[ref] = ids.get(ref, 0) + 1
    refs = [ref for ref, count in ids.items() if count == 1]
    return {"total_rows": total, "page": expected_page, "page_size": page_size,
            "rows": len(rows), "upgrade_log_refs": refs,
            "selectable_log_count": len(refs),
            "unselectable_log_count": missing,
            "ambiguous_log_reference_count": sum(count > 1 for count in ids.values()),
            "page_complete": len(rows) == min(page_size, max(0, total - (expected_page - 1) * page_size))}


def _placeholder_row(row: object) -> bool:
    if not isinstance(row, Mapping) or set(row) != {
            "modelTypeInfo", "deviceName", "mac", "currentVersion", "siteName", "type"}:
        return False
    model = row.get("modelTypeInfo")
    return (isinstance(model, Mapping) and set(model) == {"showModel", "compoundModel"} and
            model.get("showModel") == "" and model.get("compoundModel") == "" and
            all(row.get(key) == "" for key in
                ("deviceName", "mac", "currentVersion", "siteName", "type")))


def project_failed_device_page(payload: object, expected_page: int,
                               page_size: int, max_rows: int) -> dict[str, object]:
    result = validate_operation_envelope(payload)
    if set(result) - {"totalRows", "currentPage", "currentSize", "data"}:
        raise UpgradeFailureSummaryError("grid_invalid")
    rows = result.get("data")
    total, page, size = result.get("totalRows"), result.get("currentPage"), result.get("currentSize")
    if (type(total) is int and total == 0 and type(page) is int and page == 0 and
            type(size) is int and size == 0 and isinstance(rows, list) and
            len(rows) == 1 and _placeholder_row(rows[0])):
        rows = []
        page = expected_page
        size = 0
    if (type(total) is not int or not 0 <= total < (1 << 63) or
            type(page) is not int or page != expected_page or
            type(size) is not int or not 0 <= size <= page_size or
            not isinstance(rows, list) or len(rows) > page_size or
            size not in (len(rows), page_size) or len(rows) > total):
        raise UpgradeFailureSummaryError("grid_invalid")

    selected = rows[:max(0, max_rows)]
    counts = {"gateway": 0, "switch": 0, "ap": 0, "unknown": 0}
    allowed = {"modelTypeInfo", "deviceName", "mac", "currentVersion", "siteName", "type"}
    for row in selected:
        if not isinstance(row, Mapping) or set(row) - allowed:
            raise UpgradeFailureSummaryError("row_invalid")
        for key in ("deviceName", "mac", "currentVersion", "siteName"):
            value = row.get(key)
            if value is not None and (not isinstance(value, str) or len(value) > 512):
                raise UpgradeFailureSummaryError("row_invalid")
        model = row.get("modelTypeInfo")
        if model is not None:
            if (not isinstance(model, Mapping) or set(model) - {"showModel", "compoundModel"} or
                    any(not isinstance(model.get(k), str) or len(model[k]) > 512
                        for k in ("showModel", "compoundModel"))):
                raise UpgradeFailureSummaryError("row_invalid")
        device_type = row.get("type")
        if device_type in {"gateway", "switch", "ap"}:
            counts[device_type] += 1
        elif device_type is None or isinstance(device_type, str):
            counts["unknown"] += 1
        else:
            raise UpgradeFailureSummaryError("row_invalid")
    return {"total_rows": total, "rows": len(selected), "device_type_counts": counts}
