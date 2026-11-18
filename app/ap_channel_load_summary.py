"""Compact per-band summary for a single AP's channel-load result."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

try:
    from .site_batch_channel_load_summary import (
        SiteBatchChannelLoadSummaryError,
        summarize_site_batch_channel_loads,
    )
except ImportError:  # direct execution in the image
    from site_batch_channel_load_summary import (
        SiteBatchChannelLoadSummaryError,
        summarize_site_batch_channel_loads,
    )


class ApChannelLoadSummaryError(ValueError):
    """The per-AP result does not match its documented schema."""


def summarize_ap_channel_load_result(value: Any) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ApChannelLoadSummaryError("result_invalid")
    try:
        summary = summarize_site_batch_channel_loads([value])
    except SiteBatchChannelLoadSummaryError:
        raise ApChannelLoadSummaryError("result_invalid") from None
    data = summary["data"]
    assert isinstance(data, dict)
    data.pop("returned_ap_result_count", None)
    data["returned_result_count"] = 1
    return summary
