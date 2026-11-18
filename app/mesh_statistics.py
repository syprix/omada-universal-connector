"""Bounded, identifier-free projection of the documented AP mesh statistics."""
from __future__ import annotations

from typing import Any


class MeshStatisticsProjectionError(ValueError):
    """The mesh statistics response has an invalid documented value shape."""


INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
MAX_CHILD_APS = 128
MAX_CANDIDATE_PARENTS = 128
MAX_MULTI_BAND_INFO = 16
MAX_RATE_TEXT_LENGTH = 128


def _integer(value: Any, *, minimum: int = INT32_MIN,
             maximum: int = INT32_MAX) -> int:
    if (not isinstance(value, int) or isinstance(value, bool)
            or not minimum <= value <= maximum):
        raise MeshStatisticsProjectionError("response_invalid")
    return value


def _boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise MeshStatisticsProjectionError("response_invalid")
    return value


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MeshStatisticsProjectionError("response_invalid")
    return value


def _optional(source: dict[str, Any], key: str, convert) -> Any:
    if key not in source or source[key] is None:
        return None
    return convert(source[key])


def _project_uplink(value: Any) -> dict[str, Any]:
    source = _object(value)
    out: dict[str, Any] = {}
    fields = (
        ("channel", "channel", lambda v: _integer(v, minimum=0)),
        ("rssi", "rssi", _integer),
        ("snr", "snr", _integer),
        ("txRateInt", "tx_rate_mbps", _integer),
        ("rxRateInt", "rx_rate_mbps", _integer),
        ("upBytes", "up_bytes", lambda v: _integer(v, minimum=0, maximum=INT64_MAX)),
        ("downBytes", "down_bytes", lambda v: _integer(v, minimum=0, maximum=INT64_MAX)),
        ("upPackets", "up_packets", lambda v: _integer(v, minimum=0, maximum=INT64_MAX)),
        ("downPackets", "down_packets", lambda v: _integer(v, minimum=0, maximum=INT64_MAX)),
        ("activity", "activity", lambda v: _integer(v, minimum=0, maximum=INT64_MAX)),
        ("supportSpeedTest", "speed_test_supported", _boolean),
    )
    for source_key, output_key, convert in fields:
        result = _optional(source, source_key, convert)
        if result is not None:
            out[output_key] = result
    for key in ("txRate", "rxRate"):
        if key in source and source[key] is not None:
            rate = source[key]
            if not isinstance(rate, str) or len(rate) > MAX_RATE_TEXT_LENGTH:
                raise MeshStatisticsProjectionError("response_invalid")
    out["omitted_field_count"] = sum(
        1 for key, value in source.items() if value is not None and key not in {
            "channel", "rssi", "snr", "txRateInt", "rxRateInt", "upBytes",
            "downBytes", "upPackets", "downPackets", "activity", "supportSpeedTest"
        }
    )
    return out


def _project_child(value: Any) -> dict[str, Any]:
    source = _object(value)
    out: dict[str, Any] = {}
    for source_key, output_key, convert in (
        ("rssi", "rssi", _integer),
        ("supportSpeedTest", "speed_test_supported", _boolean),
        ("deviceSeriesType", "device_series_type", _integer),
    ):
        result = _optional(source, source_key, convert)
        if result is not None:
            out[output_key] = result
    out["omitted_field_count"] = sum(value is not None for value in source.values()) - len(out)
    return out


def _project_multi_band(value: Any) -> dict[str, int]:
    source = _object(value)
    out: dict[str, int] = {}
    for source_key, output_key, minimum in (
        ("radioId", "radio_id", 0),
        ("channel", "channel", 0),
        ("rssi", "rssi", INT32_MIN),
    ):
        result = _optional(source, source_key, lambda v, minimum=minimum: _integer(v, minimum=minimum))
        if result is not None:
            out[output_key] = result
    out["omitted_field_count"] = sum(value is not None for value in source.values()) - len(out)
    return out


def _project_candidate(value: Any) -> dict[str, Any]:
    source = _object(value)
    out: dict[str, Any] = {}
    for source_key, output_key, converter in (
        ("priorityStatus", "priority_status", _integer),
        ("linkStatus", "link_status", lambda v: _integer(v, minimum=0, maximum=4)),
        ("hop", "hop_count", lambda v: _integer(v, minimum=0)),
        ("childsnum", "connected_child_count", lambda v: _integer(v, minimum=0)),
        ("support5gMultiBand", "supports_5ghz_multiband", _boolean),
    ):
        result = _optional(source, source_key, converter)
        if result is not None:
            out[output_key] = result

    if "multiBandInfo" in source and source["multiBandInfo"] is not None:
        rows = source["multiBandInfo"]
        if not isinstance(rows, list):
            raise MeshStatisticsProjectionError("response_invalid")
        projected = [_project_multi_band(row) for row in rows[:MAX_MULTI_BAND_INFO]]
        omitted_rows = max(0, len(rows) - MAX_MULTI_BAND_INFO)
        out["multi_band_info"] = projected
        if omitted_rows:
            out["omitted_multi_band_info_count"] = omitted_rows
    out["omitted_field_count"] = sum(
        1 for key, value in source.items() if value is not None and key not in {
            "priorityStatus", "linkStatus", "hop", "childsnum",
            "support5gMultiBand", "multiBandInfo"
        }
    )
    return out


def project_mesh_statistics(result: Any) -> dict[str, Any]:
    """Project ``ApMeshStatisticsOpenApiVO`` without exposing device identities.

    The projection retains only documented typed diagnostic values. Unknown and
    identity-bearing fields are discarded and counted. Bounded child/candidate
    lists report omitted item counts and mark the result partial when truncated.
    Status integers remain numeric because the schema does not define their enums.
    """
    source = _object(result)
    out: dict[str, Any] = {}
    for source_key, output_key, converter in (
        ("status", "status", _integer),
        ("statusCategory", "status_category", _integer),
        ("wirelessLinked", "wireless_linked", _boolean),
        ("scanStatus", "scan_status", lambda v: _integer(v, minimum=0, maximum=3)),
    ):
        value = _optional(source, source_key, converter)
        if value is not None:
            out[output_key] = value

    partial = False
    for source_key, output_key, limit, projector in (
        ("childAps", "child_aps", MAX_CHILD_APS, _project_child),
        ("candidateParents", "candidate_parents", MAX_CANDIDATE_PARENTS, _project_candidate),
    ):
        if source_key not in source or source[source_key] is None:
            continue
        rows = source[source_key]
        if not isinstance(rows, list):
            raise MeshStatisticsProjectionError("response_invalid")
        if len(rows) > limit:
            partial = True
        out[output_key] = [projector(row) for row in rows[:limit]]
        out[output_key + "_count"] = len(rows)
        if len(rows) > limit:
            out["omitted_" + output_key + "_count"] = len(rows) - limit

    if "wirelessUplink" in source and source["wirelessUplink"] is not None:
        out["wireless_uplink"] = _project_uplink(source["wirelessUplink"])

    documented = {"status", "statusCategory", "wirelessLinked", "scanStatus",
                  "childAps", "candidateParents", "wirelessUplink"}
    omitted_fields = sum(value is not None for key, value in source.items() if key not in documented)
    out["omitted_field_count"] = omitted_fields
    out["partial"] = partial or omitted_fields > 0 or (
        out.get("wireless_uplink", {}).get("omitted_field_count", 0) > 0
    ) or any(
        item.get("omitted_field_count", 0) > 0
        for key in ("child_aps", "candidate_parents")
        for item in out.get(key, [])
    ) or any(candidate.get("omitted_multi_band_info_count", 0) > 0
             for candidate in out.get("candidate_parents", [])) or any(
        row.get("omitted_field_count", 0) > 0
        for candidate in out.get("candidate_parents", [])
        for row in candidate.get("multi_band_info", [])
    )
    return out
