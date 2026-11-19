"""Bounded, conservative channel-reuse and load summary for selected APs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
import re
from typing import Any

_REF = re.compile(r"[0-9a-f]{24}\Z")
_RADIO_BANDS = (("2g", "2g"), ("5g", "5g"), ("5g2", "5g"), ("6g", "6g"))
_LOAD_BANDS = (("2g", "2g"), ("5g", "5g"), ("6g", "6g"))
_MAX_APS = 16
_MAX_LOAD_ROWS = 256


class SiteChannelReuseError(ValueError):
    """The selected AP observations cannot be projected safely."""


def _channel(value: Any) -> int | str | None:
    if type(value) is int:
        channel = value
    elif (isinstance(value, str) and 1 <= len(value) <= 8 and
          value.isascii() and value.isdigit()):
        channel = int(value)
    else:
        return None
    return channel if 1 <= channel <= 1000 else None


def summarize_site_channel_reuse(rows: Any) -> dict[str, object]:
    """Compare documented current channels and present matching load samples.

    Equal reported channels are grouped as channel reuse. The sources do not
    define occupied channel ranges or load units, so adjacent-channel overlap
    and interference are deliberately not inferred.
    """
    if not isinstance(rows, list) or not 1 <= len(rows) <= _MAX_APS:
        raise SiteChannelReuseError("rows_invalid")
    seen: set[str] = set()
    aps: list[dict[str, object]] = []
    grouped: dict[tuple[str, int | str], list[tuple[str, str, str | None]]] = defaultdict(list)
    partial = False
    for row in rows:
        if not isinstance(row, Mapping):
            raise SiteChannelReuseError("row_invalid")
        ref = row.get("device_ref")
        if not isinstance(ref, str) or not _REF.fullmatch(ref) or ref in seen:
            raise SiteChannelReuseError("device_ref_invalid")
        seen.add(ref)
        radios, loads = row.get("radios"), row.get("channel_load")
        if not isinstance(radios, Mapping) or not isinstance(loads, Mapping):
            raise SiteChannelReuseError("source_invalid")
        radios_available = row.get("radios_available") is True
        loads_available = row.get("loads_available") is True
        partial = partial or not radios_available or not loads_available
        load_map: dict[str, dict[int | str, int]] = {}
        for source, band in _LOAD_BANDS:
            key = "channelLoads" + source
            values = loads.get(key)
            if values is None:
                partial = True
                continue
            if not isinstance(values, list) or len(values) > _MAX_LOAD_ROWS:
                raise SiteChannelReuseError("load_rows_invalid")
            found: dict[int | str, int] = {}
            for item in values:
                if not isinstance(item, Mapping):
                    partial = True
                    continue
                channel, load = _channel(item.get("channel")), item.get("load")
                if channel is None or type(load) is not int or not -(2**31) <= load < 2**31:
                    partial = True
                    continue
                found[channel] = load
            load_map[band] = found
        bands: list[dict[str, object]] = []
        for source, band in _RADIO_BANDS:
            detail = radios.get("wp" + source)
            if detail is None:
                continue
            if not isinstance(detail, Mapping):
                partial = True
                continue
            actual = _channel(detail.get("actualChannel"))
            width = detail.get("bandWidth")
            if width is not None and (not isinstance(width, str) or len(width) > 32):
                partial = True
                width = None
            entry: dict[str, object] = {"band": band}
            if actual is not None:
                entry["channel"] = actual
            else:
                entry["channel_status"] = "unknown_or_auto"
                partial = True
            if width is not None:
                entry["reported_bandwidth"] = width
            else:
                entry["bandwidth_status"] = "unavailable"
                partial = True
            if actual is not None:
                grouped[(band, actual)].append((ref, source, width))
            if actual is not None and actual in load_map.get(band, {}):
                entry["reported_channel_load"] = load_map[band][actual]
            else:
                entry["reported_channel_load"] = None
                entry["channel_load_status"] = "unavailable_for_channel"
                partial = True
            bands.append(entry)
        aps.append({"device_ref": ref, "bands": bands,
                    "radio_detail_status": "available" if radios_available else "unavailable",
                    "channel_load_status": "available" if loads_available else "unavailable"})

    reuse = [{"band": band, "channel": channel,
              "device_refs": sorted({ref for ref, _radio, _width in radios}),
              "access_point_count": len({ref for ref, _radio, _width in radios}),
              "radio_count": len(radios),
              "reported_bandwidths": sorted({width for _ref, _radio, width in radios
                                              if width is not None}),
              "bandwidth_unavailable_count": sum(width is None for _ref, _radio, width in radios),
              "assessment": "same_reported_channel_reuse"}
             for (band, channel), radios in sorted(grouped.items(), key=lambda x: (x[0][0], str(x[0][1])))
             if len({ref for ref, _radio, _width in radios}) > 1]
    return {"status": "ok", "resource": "site_channel_reuse_summary",
            "selected_access_point_count": len(aps), "access_points": aps,
            "same_channel_reuse": reuse,
            "overlap_assessment": "adjacent_channel_overlap_unknown",
            "interference_assessment": "not_inferred_from_load",
            "partial": partial}
