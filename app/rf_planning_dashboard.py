"""Redacted RF planning dashboard projection for site WLAN diagnosis."""
from __future__ import annotations


class RfPlanningDashboardError(ValueError):
    """The upstream dashboard exceeds the accepted bounds."""

    def __init__(self, code: str = "rf_planning_dashboard_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_FIELDS = 24
_MAX_TREND_POINTS = 256
_MAX_AP_ROWS = 256
_MAX_KEY_LENGTH = 128
_INT64_MAX = 2**63 - 1
_INT32_MAX = 2**31 - 1
_BANDS = {
    "wlanOptDashBoardDetail2g": "2g",
    "wlanOptDashBoardDetail5g": "5g",
    "wlanOptDashBoardDetail6g": "6g",
}
_CCI_TREND = (
    "strongInterferenceApNum", "strongInterferenceApPercent",
    "moderateInterferenceApNum", "moderateInterferenceApPercent",
    "weakInterferenceApNum", "weakInterferenceApPercent",
)
_DENSITY_TREND = (
    "denseApNum", "denseApPercent", "moderateApNum", "moderateApPercent",
    "sparseApNum", "sparseApPercent",
)
_CCI_GROUPS = {
    "high": "currentHighCciInfoList",
    "medium": "currentMediumCciInfoList",
    "low": "currentLowCciInfoList",
    "no_data": "noDataList",
}
_DENSITY_GROUPS = {
    "high": "currentApDensityHighInfo",
    "medium": "currentApDensityMediumInfo",
    "low": "currentApDensityLowInfo",
    "no_data": "noDataList",
}


def _omit(omitted: set[str], count: list[int], category: str, amount: int = 1) -> None:
    omitted.add(category)
    count[0] += amount


def _keys(value: dict[object, object]) -> None:
    if len(value) > _MAX_FIELDS or any(
            not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH for key in value):
        raise RfPlanningDashboardError()


def _trend(raw: object, field: str, values: tuple[str, ...], label: str,
           missing: list[str], omitted: set[str], omitted_count: list[int],
           start_ms: int | None, end_ms: int | None
           ) -> list[dict[str, int]] | None:
    if raw is None:
        missing.append(label)
        return None
    if not isinstance(raw, dict):
        _omit(omitted, omitted_count, "invalid_trends")
        return None
    _keys(raw)
    if field not in raw:
        missing.append(label + "." + field)
        return None
    rows = raw[field]
    if not isinstance(rows, list):
        _omit(omitted, omitted_count, "invalid_trends")
        return None
    if len(rows) > _MAX_TREND_POINTS:
        raise RfPlanningDashboardError()
    result: list[dict[str, int]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            _omit(omitted, omitted_count, "invalid_trend_points")
            continue
        _keys(row)
        timestamp = row.get("time")
        valid_timestamp = type(timestamp) is int and 0 <= timestamp <= _INT64_MAX
        if (valid_timestamp and start_ms is not None and end_ms is not None and
                not start_ms <= timestamp <= end_ms):
            _omit(omitted, omitted_count, "out_of_window_trend_points")
            continue
        point: dict[str, int] = {}
        for name in ("time", *values):
            if name not in row:
                missing.append(f"{label}.{field}[{index}].{name}")
                continue
            value = row[name]
            if name == "time":
                valid = type(value) is int and 0 <= value <= _INT64_MAX
            elif name.endswith("Percent"):
                valid = type(value) is int and 0 <= value <= 100
            else:
                valid = type(value) is int and 0 <= value <= _INT32_MAX
            if valid:
                target = "time_ms" if name == "time" else _camel_to_snake(name)
                point[target] = value
            else:
                _omit(omitted, omitted_count, "invalid_trend_values")
        known = {"time", *values}
        extras = sum(1 for key in row if key not in known)
        if extras:
            _omit(omitted, omitted_count, "unknown_fields", extras)
        if start_ms is not None and end_ms is not None and not valid_timestamp:
            _omit(omitted, omitted_count, "missing_trend_time")
            continue
        result.append(point)
    extras = sum(1 for key in raw if key != field)
    if extras:
        _omit(omitted, omitted_count, "unknown_fields", extras)
    return result


def _camel_to_snake(value: str) -> str:
    out: list[str] = []
    for char in value:
        if char.isupper():
            out.extend(("_", char.lower()))
        else:
            out.append(char)
    return "".join(out).lstrip("_")


def _group_counts(raw: object, groups: dict[str, str], label: str,
                  missing: list[str], omitted: set[str], omitted_count: list[int]
                  ) -> dict[str, int] | None:
    if raw is None:
        missing.append(label)
        return None
    if not isinstance(raw, dict):
        _omit(omitted, omitted_count, "invalid_current_details")
        return None
    _keys(raw)
    result: dict[str, int] = {}
    for output, source in groups.items():
        rows = raw.get(source)
        if source not in raw:
            missing.append(f"{label}.{source}")
        elif not isinstance(rows, list):
            _omit(omitted, omitted_count, "invalid_current_details")
        elif len(rows) > _MAX_AP_ROWS:
            raise RfPlanningDashboardError()
        else:
            valid_rows = 0
            for row in rows:
                if isinstance(row, dict):
                    _keys(row)
                    valid_rows += 1
                    if any(key not in {"name", "mac", "model", "modelVersion", "type",
                                       "noData", "noDataReason", "channel", "channel5g2",
                                       "totalLevel", "totalLevelPercent", "inSiteLevel",
                                       "inSiteLevelPercent", "outSiteLevel", "outSiteLevelPercent",
                                       "neighborApNum", "neighborApPercent"} for key in row):
                        _omit(omitted, omitted_count, "unknown_fields",
                              sum(1 for key in row if key not in {"name", "mac", "model",
                                  "modelVersion", "type", "noData", "noDataReason", "channel",
                                  "channel5g2", "totalLevel", "totalLevelPercent", "inSiteLevel",
                                  "inSiteLevelPercent", "outSiteLevel", "outSiteLevelPercent",
                                  "neighborApNum", "neighborApPercent"}))
                else:
                    _omit(omitted, omitted_count, "invalid_current_details")
            result[output] = valid_rows
    known = set(groups.values())
    extras = sum(1 for key in raw if key not in known)
    if extras:
        _omit(omitted, omitted_count, "unknown_fields", extras)
    return result


def project_rf_planning_dashboard(raw: object, *, start_ms: int | None = None,
                                  end_ms: int | None = None) -> dict[str, object]:
    """Return aggregate CCI/AP-density trends and redacted current counts."""
    if not isinstance(raw, dict):
        raise RfPlanningDashboardError()
    if ((start_ms is None) != (end_ms is None) or
            (start_ms is not None and (type(start_ms) is not int or type(end_ms) is not int or
                                       start_ms < 0 or end_ms < start_ms or end_ms > _INT64_MAX))):
        raise RfPlanningDashboardError()
    _keys(raw)
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = [0]
    bands: dict[str, object] = {}
    for source, band in _BANDS.items():
        if source not in raw:
            missing.append(source)
            continue
        details = raw[source]
        if not isinstance(details, dict):
            _omit(omitted, omitted_count, "invalid_bands")
            continue
        _keys(details)
        cci_trend = _trend(details.get("cciTrendDetail"), "cciTrendItemList",
                           _CCI_TREND, band + ".cci_trend", missing, omitted,
                           omitted_count, start_ms, end_ms)
        cci_current = _group_counts(details.get("cciCurrentDetail"), _CCI_GROUPS,
                                    band + ".cci_current", missing, omitted, omitted_count)
        density_trend = _trend(details.get("apDensityTrendDetail"), "apDensityItemList",
                               _DENSITY_TREND, band + ".ap_density_trend", missing, omitted,
                               omitted_count, start_ms, end_ms)
        density_current = _group_counts(details.get("apDensityCurrentDetail"), _DENSITY_GROUPS,
                                        band + ".ap_density_current", missing, omitted,
                                        omitted_count)
        band_data: dict[str, object] = {}
        if cci_trend is not None:
            band_data["cci_trend"] = cci_trend
        if cci_current is not None:
            band_data["cci_current_ap_counts"] = cci_current
        if density_trend is not None:
            band_data["ap_density_trend"] = density_trend
        if density_current is not None:
            band_data["ap_density_current_counts"] = density_current
        bands[band] = band_data
        extras = sum(1 for key in details if key not in {"cciTrendDetail", "cciCurrentDetail",
                         "apDensityTrendDetail", "apDensityCurrentDetail"})
        if extras:
            _omit(omitted, omitted_count, "unknown_fields", extras)
    extras = sum(1 for key in raw if key not in _BANDS)
    if extras:
        _omit(omitted, omitted_count, "unknown_fields", extras)
    return {
        "status": "ok",
        "resource": "rf_planning_dashboard",
        "data": {"bands": bands},
        "partial": bool(missing or omitted_count[0]),
        "missing_fields": missing,
        "omitted_field_count": omitted_count[0],
        "omitted_fields": sorted(omitted),
    }
