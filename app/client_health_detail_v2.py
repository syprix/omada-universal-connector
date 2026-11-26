from __future__ import annotations

from typing import Any


MAX_POINTS_PER_SERIES = 64
MAX_INCIDENTS_PER_DIMENSION = 32
_MAX_INT64 = 2**63 - 1
_LONG_TIME_VALUE_FIELDS = frozenset({"pastTxRate", "pastRxRate"})


class ClientHealthDetailV2Error(ValueError):
    """Raised when a version-two client health response is not an object."""


def _integer(value: Any, minimum: int = -_MAX_INT64 - 1,
             maximum: int = _MAX_INT64) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _series(
    value: Any,
    *,
    start_ms: int | None,
    end_ms: int | None,
    number_min: int,
    number_max: int,
) -> tuple[dict[str, object] | None, bool, int]:
    if not isinstance(value, list):
        return None, True, 0
    partial = len(value) > MAX_POINTS_PER_SERIES
    points: list[tuple[int, int]] = []
    invalid = 0
    for item in value[:MAX_POINTS_PER_SERIES]:
        if not isinstance(item, dict) or len(item) > 4:
            invalid += 1
            partial = True
            continue
        if set(item) - {"time", "pastNum"}:
            invalid += 1
            partial = True
        timestamp, number = item.get("time"), item.get("pastNum")
        if (not _integer(timestamp, 0, _MAX_INT64) or
                not _integer(number, number_min, number_max)):
            invalid += 1
            partial = True
            continue
        if ((start_ms is not None and timestamp < start_ms) or
                (end_ms is not None and timestamp > end_ms)):
            invalid += 1
            partial = True
            continue
        points.append((timestamp, number))
    if not points:
        return {"sample_count": 0}, partial, invalid
    values = [point[1] for point in points]
    times = [point[0] for point in points]
    return {
        "sample_count": len(points),
        "first_time_ms": min(times),
        "last_time_ms": max(times),
        "minimum": min(values),
        "maximum": max(values),
        "average": sum(values) // len(values),
    }, partial, invalid


def _dimension(
    raw: Any,
    *,
    series_fields: dict[str, str],
    scalar_fields: dict[str, tuple[str, int, int]],
    start_ms: int | None,
    end_ms: int | None,
) -> tuple[dict[str, object], bool, int, int, int]:
    if not isinstance(raw, dict) or len(raw) > 96:
        return {}, True, 1, 0, 0
    allowed = {"summaryScore", "support", "incidents", *series_fields, *scalar_fields}
    partial = bool(set(raw) - allowed)
    invalid = len(set(raw) - allowed)
    output: dict[str, object] = {}
    score = raw.get("summaryScore")
    if score is not None:
        if _integer(score, -(2**31), 2**31 - 1):
            output["summary_score"] = score
        else:
            invalid += 1
            partial = True
    support = raw.get("support")
    if support is not None:
        if isinstance(support, bool):
            output["supported"] = support
        else:
            invalid += 1
            partial = True

    for source, target in scalar_fields.items():
        key, minimum, maximum = target
        value = raw.get(source)
        if value is not None:
            if _integer(value, minimum, maximum):
                output[key] = value
            else:
                invalid += 1
                partial = True

    series_output: dict[str, object] = {}
    for source, target in series_fields.items():
        if source not in raw or raw[source] is None:
            continue
        number_min, number_max = (
            (-2**63, _MAX_INT64) if source in _LONG_TIME_VALUE_FIELDS
            else (-2**31, 2**31 - 1))
        projected, series_partial, series_invalid = _series(
            raw[source], start_ms=start_ms, end_ms=end_ms,
            number_min=number_min, number_max=number_max)
        partial |= series_partial
        invalid += series_invalid
        if projected is not None:
            series_output[target] = projected
    if series_output:
        output["series"] = series_output

    incident_entries = 0
    incident_occurrences = 0
    incident_omitted = 0
    incidents = raw.get("incidents")
    if "incidents" in raw:
        occurrences_complete = True
        if incidents is None:
            # The source schema says a null incident collection means no incidents.
            output["incident_entry_count"] = 0
            output["incident_occurrence_count"] = 0
        elif not isinstance(incidents, list):
            invalid += 1
            partial = True
            occurrences_complete = False
            output["incident_entry_count"] = 0
            output["incident_occurrence_count"] = None
        else:
            if len(incidents) > MAX_INCIDENTS_PER_DIMENSION:
                incident_omitted = len(incidents) - MAX_INCIDENTS_PER_DIMENSION
                partial = True
                occurrences_complete = False
            for item in incidents[:MAX_INCIDENTS_PER_DIMENSION]:
                if not isinstance(item, dict) or len(item) > 32:
                    invalid += 1
                    partial = True
                    occurrences_complete = False
                    continue
                incident_entries += 1
                count = item.get("count")
                if count is None:
                    partial = True
                    occurrences_complete = False
                elif _integer(count, 0, 1_000_000):
                    incident_occurrences += count
                else:
                    invalid += 1
                    partial = True
                    occurrences_complete = False
            output["incident_entry_count"] = incident_entries
            output["incident_occurrence_count"] = (
                incident_occurrences if occurrences_complete else None)
    return (output, partial, invalid, incident_entries, incident_omitted)


_DIMENSIONS: dict[str, tuple[str, dict[str, str], dict[str, tuple[str, int, int]]]] = {
    "onboardingTime": ("onboarding_time", {
        "assocTime": "association_time",
        "authTime": "authorization_time",
        "dhcpTime": "dhcp_time",
        "dnsTime": "dns_time",
    }, {
        "averageAssocTime": ("average_association_time", 0, 2**31 - 1),
        "averageAuthTime": ("average_authorization_time", 0, 2**31 - 1),
        "averageDhcpTime": ("average_dhcp_time", 0, 2**31 - 1),
        "averageDnsTime": ("average_dns_time", 0, 2**31 - 1),
    }),
    "bandRssi": ("band_rssi", {
        "pastNums2g": "2g",
        "pastNums5g": "5g",
        "pastNums6g": "6g",
    }, {
        "averageNum2g": ("average_2g", -(2**31), 2**31 - 1),
        "averageNum5g": ("average_5g", -(2**31), 2**31 - 1),
        "averageNum6g": ("average_6g", -(2**31), 2**31 - 1),
    }),
    "dataRate": ("data_rate", {
        "pastTxRate": "transmit_rate",
        "pastRxRate": "receive_rate",
    }, {
        "averageTxRate": ("average_transmit_rate", 0, _MAX_INT64),
        "averageRxRate": ("average_receive_rate", 0, _MAX_INT64),
    }),
    "snr": ("snr", {"pastNums": "values"}, {
        "averageNum": ("average", -(2**31), 2**31 - 1),
    }),
    "connectScore": ("connect_score", {}, {
        "connectStatus": ("connect_status_code", -(2**31), 2**31 - 1),
    }),
    "linkErrorScore": ("link_error_score", {"pastNums": "values"}, {
        "averageNum": ("average", -(2**31), 2**31 - 1),
    }),
    "incident": ("incident", {}, {
        "incidentNum": ("incident_count", 0, 1_000_000),
    }),
}


def project_client_health_detail_v2(
    result: Any, *, start_ms: int | None = None, end_ms: int | None = None,
) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 24:
        raise ClientHealthDetailV2Error("response_invalid")
    if ((start_ms is not None and not _integer(start_ms, 0, _MAX_INT64)) or
            (end_ms is not None and not _integer(end_ms, 0, _MAX_INT64)) or
            (start_ms is not None and end_ms is not None and start_ms >= end_ms)):
        raise ClientHealthDetailV2Error("window_invalid")
    allowed = {"score", *list(_DIMENSIONS)}
    partial = bool(set(result) - allowed)
    unknown = len(set(result) - allowed)
    invalid = 0
    data: dict[str, object] = {}

    score = result.get("score")
    if score is not None:
        if _integer(score, -(2**31), 2**31 - 1):
            data["score"] = score
        else:
            invalid += 1
            partial = True

    dimensions: dict[str, object] = {}
    incident_entries = 0
    incident_omitted = 0
    for source, (target, series, scalars) in _DIMENSIONS.items():
        if source not in result or result[source] is None:
            continue
        projected, dim_partial, dim_invalid, dim_incident_entries, dim_incident_omitted = _dimension(
            result[source], series_fields=series, scalar_fields=scalars,
            start_ms=start_ms, end_ms=end_ms)
        dimensions[target] = projected
        partial |= dim_partial
        invalid += dim_invalid
        incident_entries += dim_incident_entries
        incident_omitted += dim_incident_omitted
    data["dimensions"] = dimensions

    return {
        "status": "partial" if partial else "ok",
        "partial": partial,
        "health_version": 2,
        "score": data.get("score"),
        "dimensions": dimensions,
        "dimension_count": len(dimensions),
        "incident_entry_count": incident_entries,
        "omitted_incident_entry_count": incident_omitted,
        "invalid_entry_or_field_count": invalid,
        "unknown_field_count": unknown,
        "omitted_series_limit": sum(
            max(0, len(result.get(source, {}).get(field, [])) - MAX_POINTS_PER_SERIES)
            for source, (_target, series, _scalars) in _DIMENSIONS.items()
            if isinstance(result.get(source), dict)
            for field in series
            if isinstance(result[source].get(field), list)
        ),
        "source_contract_scope": "hardware_controller_and_cbc_6_3_only",
    }
