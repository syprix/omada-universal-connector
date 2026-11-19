from __future__ import annotations

import unittest

from app.site_channel_reuse_summary import (
    SiteChannelReuseError, summarize_site_channel_reuse,
)


class SiteChannelReuseTests(unittest.TestCase):
    def row(self, suffix: str, channel: int | str, load: int) -> dict[str, object]:
        return {
            "device_ref": suffix * 24,
            "radios": {"wp2g": {"actualChannel": str(channel), "bandWidth": "20MHz"}},
            "channel_load": {"channelLoads2g": [{"channel": int(channel), "load": load}],
                             "channelLoads5g": [], "channelLoads6g": []},
            "radios_available": True, "loads_available": True,
        }

    def test_groups_equal_reported_channels_and_keeps_measurements(self):
        result = summarize_site_channel_reuse([
            self.row("a", 6, 32), self.row("b", "6", 55), self.row("c", 11, 3),
        ])
        self.assertEqual(result["same_channel_reuse"], [{
            "band": "2g", "channel": 6, "device_refs": ["a" * 24, "b" * 24],
            "access_point_count": 2, "radio_count": 2,
            "reported_bandwidths": ["20MHz"], "bandwidth_unavailable_count": 0,
            "assessment": "same_reported_channel_reuse",
        }])
        self.assertEqual(result["access_points"][0]["bands"][0]["reported_channel_load"], 32)
        self.assertEqual(result["overlap_assessment"], "adjacent_channel_overlap_unknown")
        self.assertEqual(result["interference_assessment"], "not_inferred_from_load")
        self.assertFalse(result["partial"])

    def test_missing_sources_and_auto_channel_are_visible_as_partial(self):
        row = self.row("a", "0", 9)
        row["radios"] = {"wp2g": {"actualChannel": "auto"}}
        row["loads_available"] = False
        result = summarize_site_channel_reuse([row])
        band = result["access_points"][0]["bands"][0]
        self.assertEqual(band["channel_status"], "unknown_or_auto")
        self.assertIsNone(band["reported_channel_load"])
        self.assertTrue(result["partial"])

    def test_numeric_string_channels_use_the_same_valid_range_as_integers(self):
        valid_a = self.row("a", "6", 4)
        valid_b = self.row("b", 6, 7)
        zero_a = self.row("c", "0", 1)
        zero_b = self.row("d", "0", 2)
        high_a = self.row("e", "1001", 3)
        high_b = self.row("f", 1001, 5)
        result = summarize_site_channel_reuse(
            [valid_a, valid_b, zero_a, zero_b, high_a, high_b])
        self.assertEqual(result["same_channel_reuse"], [{
            "band": "2g", "channel": 6, "device_refs": ["a" * 24, "b" * 24],
            "access_point_count": 2, "radio_count": 2,
            "reported_bandwidths": ["20MHz"], "bandwidth_unavailable_count": 0,
            "assessment": "same_reported_channel_reuse",
        }])
        by_ref = {ap["device_ref"]: ap for ap in result["access_points"]}
        for suffix in ("c", "d", "e", "f"):
            self.assertEqual(by_ref[suffix * 24]["bands"][0]["channel_status"],
                             "unknown_or_auto")
        self.assertEqual(by_ref["a" * 24]["bands"][0]["channel"], 6)

    def test_rejects_duplicate_refs_and_oversized_inputs(self):
        row = self.row("a", 1, 2)
        with self.assertRaises(SiteChannelReuseError):
            summarize_site_channel_reuse([row, row])
        with self.assertRaises(SiteChannelReuseError):
            summarize_site_channel_reuse([self.row("a", 1, 2)] * 17)


if __name__ == "__main__":
    unittest.main()
