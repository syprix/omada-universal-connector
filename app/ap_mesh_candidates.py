"""Redacted aggregate projection of AP mesh candidate-parent rows."""
from __future__ import annotations


class ApMeshCandidatesError(ValueError):
    """Candidate-parent rows exceed the documented projection limits."""


_ROW = frozenset({"mac", "name", "linkStatus", "hop", "childsnum",
                  "recommend", "recommendRadioId", "multiBandInfo"})
_BAND = frozenset({"radioId", "channel", "rssi"})
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_MAX_ROWS = 2000
_MAX_BANDS_PER_ROW = 16


def _int32(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def summarize_ap_mesh_candidates(grid: object) -> dict[str, object]:
    if not isinstance(grid, dict) or len(grid) > 8:
        raise ApMeshCandidatesError()
    rows = grid.get("data")
    total = grid.get("totalRows")
    if (not isinstance(rows, list) or len(rows) > _MAX_ROWS or
            type(total) is not int or not 0 <= total <= _MAX_ROWS or
            type(grid.get("currentPage")) is not int or grid["currentPage"] < 1 or
            type(grid.get("currentSize")) is not int or grid["currentSize"] < 0):
        raise ApMeshCandidatesError()
    link_status: dict[int, int] = {}
    hop_counts: dict[int, int] = {}
    child_total = 0
    recommend_true = recommend_false = 0
    recommended_radio_counts: dict[int, int] = {}
    radio_counts: dict[int, int] = {}
    channel_counts: dict[int, int] = {}
    rssi_counts: dict[int, int] = {}
    redacted = invalid = missing = 0
    unknown = sum(1 for key in grid if key not in
                  {"data", "totalRows", "currentPage", "currentSize"})
    for row in rows:
        if not isinstance(row, dict) or len(row) > 32:
            invalid += 1
            continue
        unknown += sum(1 for key in row if key not in _ROW)
        redacted += sum(1 for key in ("mac", "name") if key in row)
        values = (("linkStatus", link_status, {0, 1, 2, 3, 4}),
                  ("hop", hop_counts, None))
        for field, target, allowed in values:
            value = row.get(field)
            if field not in row:
                missing += 1
            elif _int32(value) and (allowed is None or value in allowed):
                target[value] = target.get(value, 0) + 1
            else:
                invalid += 1
        children = row.get("childsnum")
        if "childsnum" not in row:
            missing += 1
        elif _int32(children) and 0 <= children <= 100_000:
            child_total += children
        else:
            invalid += 1
        recommend = row.get("recommend")
        if "recommend" not in row:
            missing += 1
        elif type(recommend) is bool:
            if recommend:
                recommend_true += 1
            else:
                recommend_false += 1
        else:
            invalid += 1
        rec_radio = row.get("recommendRadioId")
        if "recommendRadioId" in row:
            if _int32(rec_radio):
                recommended_radio_counts[rec_radio] = recommended_radio_counts.get(rec_radio, 0) + 1
            else:
                invalid += 1
        bands = row.get("multiBandInfo")
        if "multiBandInfo" not in row:
            missing += 1
        elif not isinstance(bands, list) or len(bands) > _MAX_BANDS_PER_ROW:
            invalid += 1
        else:
            for band in bands:
                if not isinstance(band, dict) or len(band) > 16:
                    invalid += 1
                    continue
                unknown += sum(1 for key in band if key not in _BAND)
                for field, target in (("radioId", radio_counts),
                                      ("channel", channel_counts),
                                      ("rssi", rssi_counts)):
                    value = band.get(field)
                    if field not in band:
                        missing += 1
                    elif _int32(value):
                        target[value] = target.get(value, 0) + 1
                    else:
                        invalid += 1
    partial = bool(missing or invalid or unknown or len(rows) != total)
    return {
        "status": "ok", "resource": "ap_mesh_candidates",
        "count": len(rows), "total_rows": total,
        "link_status_counts": dict(sorted(link_status.items())),
        "hop_counts": dict(sorted(hop_counts.items())),
        "child_ap_total": child_total,
        "recommended_count": recommend_true, "not_recommended_count": recommend_false,
        "recommended_radio_id_counts": dict(sorted(recommended_radio_counts.items())),
        "radio_id_counts": dict(sorted(radio_counts.items())),
        "channel_counts": dict(sorted(channel_counts.items())),
        "rssi_value_counts": dict(sorted(rssi_counts.items())),
        "redacted_field_count": redacted, "unknown_field_count": unknown,
        "invalid_field_count": invalid, "missing_field_count": missing,
        "partial": partial,
    }
