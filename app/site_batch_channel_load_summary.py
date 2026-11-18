"""Bounded, identity-free summary for batch interference channel loads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SiteBatchChannelLoadSummaryError(ValueError):
    """The upstream channel-load response cannot be safely summarized."""


_BANDS = (("channelLoads2g", "2g"), ("channelLoads5g", "5g"),
          ("channelLoads6g", "6g"))
_BAND_FIELDS = frozenset(name for name, _band in _BANDS)
_MAX_AP_ROWS = 128
_MAX_CHANNEL_ROWS = 256
_INT32_MAX = 2**31 - 1


def summarize_site_batch_channel_loads(value: Any) -> dict[str, object]:
    """Return aggregate load bounds per band; omit channel and device identities."""
    if not isinstance(value, list) or len(value) > _MAX_AP_ROWS:
        raise SiteBatchChannelLoadSummaryError("result_invalid")

    aggregates: dict[str, dict[str, object]] = {
        band: {"returned_channel_count": 0, "minimum_load": None,
               "maximum_load": None, "average_load": None}
        for _source, band in _BANDS
    }
    partial = False
    omitted = 0
    unknown = 0
    for row in value:
        if not isinstance(row, Mapping):
            partial = True
            omitted += 1
            continue
        row_unknown = sum(key not in _BAND_FIELDS for key in row)
        unknown += row_unknown
        partial = partial or bool(row_unknown)
        for source, band in _BANDS:
            if source not in row or row[source] is None:
                partial = True
                continue
            values = row[source]
            if not isinstance(values, list) or len(values) > _MAX_CHANNEL_ROWS:
                raise SiteBatchChannelLoadSummaryError("channel_list_invalid")
            target = aggregates[band]
            count = int(target["returned_channel_count"])
            loads: list[int] = []
            for item in values:
                if not isinstance(item, Mapping):
                    partial = True
                    omitted += 1
                    continue
                item_unknown = sum(key not in {"channel", "load"} for key in item)
                unknown += item_unknown
                partial = partial or bool(item_unknown)
                channel = item.get("channel")
                load = item.get("load")
                if (isinstance(channel, bool) or not isinstance(channel, int) or
                        not -_INT32_MAX - 1 <= channel <= _INT32_MAX or
                        isinstance(load, bool) or not isinstance(load, int) or
                        not -_INT32_MAX - 1 <= load <= _INT32_MAX):
                    partial = True
                    omitted += 1
                    continue
                loads.append(load)
            if loads:
                combined_count = count + len(loads)
                old_min = target["minimum_load"]
                old_max = target["maximum_load"]
                old_avg = target["average_load"]
                total = (float(old_avg) * count if count and old_avg is not None else 0.0)
                total += sum(loads)
                target["returned_channel_count"] = combined_count
                target["minimum_load"] = min([x for x in (old_min, *loads) if x is not None])
                target["maximum_load"] = max([x for x in (old_max, *loads) if x is not None])
                target["average_load"] = total / combined_count

    return {"data": {"bands": aggregates, "returned_ap_result_count": len(value),
                     "omitted_value_count": omitted, "unknown_field_count": unknown},
            "partial": partial}
