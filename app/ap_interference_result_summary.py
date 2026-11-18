"""Redacted summary for the recursive per-AP interference result."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

try:
    from .site_batch_interference_result_summary import (
        SiteBatchInterferenceResultSummaryError,
        summarize_site_batch_interferences,
    )
except ImportError:  # direct execution in the image
    from site_batch_interference_result_summary import (
        SiteBatchInterferenceResultSummaryError,
        summarize_site_batch_interferences,
    )


class ApInterferenceResultSummaryError(ValueError):
    """The per-AP result does not match its documented recursive schema."""


def summarize_ap_interference_result(value: Any) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ApInterferenceResultSummaryError("result_invalid")
    try:
        return summarize_site_batch_interferences([value])
    except SiteBatchInterferenceResultSummaryError:
        raise ApInterferenceResultSummaryError("result_invalid") from None
