"""Compact, schema-aware summary of an AP's supported Wi-Fi channels."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ApAvailableChannelSummaryError(ValueError):
    """The available-channel response cannot be safely projected."""


_RADIOS = {0: "2_4ghz", 1: "5ghz_1", 2: "5ghz_2", 3: "6ghz"}
_RADIO_FIELDS = frozenset({"radioId", "apChannelDetailList"})
_CHANNEL_FIELDS = frozenset({"channel", "freq", "availableChannelWidthList", "index"})
_INT32_MIN, _INT32_MAX = -(2**31), 2**31 - 1
_MAX_RADIOS = 8
_MAX_CHANNELS_PER_RADIO = 256
_MAX_WIDTHS_PER_CHANNEL = 16


def _integer(value: Any) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def summarize_ap_available_channels(value: Any) -> dict[str, object]:
    """Compact object keys while retaining each channel's documented values."""
    if not isinstance(value, list) or len(value) > _MAX_RADIOS:
        raise ApAvailableChannelSummaryError("result_invalid")

    radios: list[dict[str, object]] = []
    partial = False
    omitted = unknown = unknown_radio = 0
    for radio in value:
        if not isinstance(radio, Mapping):
            partial = True
            omitted += 1
            continue
        unknown += sum(key not in _RADIO_FIELDS for key in radio)
        partial = partial or any(key not in _RADIO_FIELDS for key in radio)
        radio_id = radio.get("radioId")
        if not _integer(radio_id) or radio_id not in _RADIOS:
            partial = True
            unknown_radio += 1
            continue
        if "apChannelDetailList" not in radio or radio["apChannelDetailList"] is None:
            partial = True
            continue
        channels = radio["apChannelDetailList"]
        if not isinstance(channels, list) or len(channels) > _MAX_CHANNELS_PER_RADIO:
            raise ApAvailableChannelSummaryError("channel_list_invalid")
        compact_channels: list[list[object]] = []
        omitted_channels = 0
        for channel in channels:
            if not isinstance(channel, Mapping):
                partial = True
                omitted += 1
                omitted_channels += 1
                continue
            channel_unknown = sum(key not in _CHANNEL_FIELDS for key in channel)
            unknown += channel_unknown
            partial = partial or bool(channel_unknown)
            row: list[object] = []
            for name in ("channel", "freq", "index"):
                item = channel.get(name)
                if _integer(item):
                    row.append(item)
                else:
                    row.append(None)
                    partial = True
            widths = channel.get("availableChannelWidthList")
            if widths is None:
                row.append(None)
                partial = True
            elif not isinstance(widths, list) or len(widths) > _MAX_WIDTHS_PER_CHANNEL:
                row.append(None)
                partial = True
            else:
                valid_widths = [item for item in widths if _integer(item)]
                if len(valid_widths) != len(widths):
                    partial = True
                row.append(valid_widths)
            if all(item is None for item in row[:3]):
                omitted += 1
                omitted_channels += 1
            compact_channels.append(row)
        radios.append({"band": _RADIOS[radio_id], "radio_id": radio_id,
                       "channels": compact_channels,
                       "omitted_channel_count": omitted_channels})

    return {"data": {"radios": radios, "omitted_value_count": omitted,
                     "unknown_radio_count": unknown_radio, "unknown_field_count": unknown},
            "partial": partial}
