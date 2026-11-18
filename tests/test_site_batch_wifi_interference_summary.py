from __future__ import annotations

import unittest

from app.site_batch_wifi_interference_summary import (
    SiteBatchWifiInterferenceSummaryError,
    summarize_site_batch_wifi_interferences,
)


def _row(index: int = 0) -> dict[str, object]:
    return {"id": f"private-id-{index}", "bssid": f"00:11:22:33:44:{index:02x}",
            "ssid": "Private Network", "radioId": 0, "channel": 6, "mode": 4,
            "security": 3, "beacon": 100, "signal": -63,
            "lastSeen": 1_800_000_000_000, "nearestAp": "AA:BB:CC:DD:EE:FF",
            "bandWidth": 20}


class SiteBatchWifiInterferenceSummaryTests(unittest.TestCase):
    def test_projects_counts_and_keeps_additional_pages_explicit(self):
        result = summarize_site_batch_wifi_interferences({
            "totalRows": 125, "currentPage": 1, "currentSize": 100,
            "data": [_row(i) for i in range(100)],
        })
        data = result["data"]
        self.assertEqual(data["total_rows"], 125)
        self.assertEqual(data["returned_interference_count"], 100)
        self.assertTrue(data["has_more"])
        self.assertFalse(data["coverage_unknown"])
        self.assertEqual(data["radio_id_counts"], {"0": 100})
        self.assertEqual(data["channel_counts"], {"6": 100})
        self.assertEqual(data["security_type_counts"], {"3": 100})
        self.assertEqual(data["signal_min"], -63)
        self.assertTrue(result["partial"])
        for private in ("private-id-0", "Private Network", "00:11:22:33:44:00",
                        "AA:BB:CC:DD:EE:FF"):
            self.assertNotIn(private, repr(result))

    def test_known_last_page_is_complete_and_unknown_total_is_not(self):
        complete = summarize_site_batch_wifi_interferences({
            "totalRows": 1, "currentPage": 1, "currentSize": 100, "data": [_row()]})
        self.assertFalse(complete["data"]["has_more"])
        self.assertFalse(complete["data"]["coverage_unknown"])
        self.assertFalse(complete["partial"])
        unknown = summarize_site_batch_wifi_interferences({"currentPage": 1, "data": []})
        self.assertTrue(unknown["data"]["coverage_unknown"])
        self.assertIsNone(unknown["data"]["total_rows"])
        self.assertTrue(unknown["partial"])

    def test_marks_invalid_unknown_and_actual_overflow_separately(self):
        result = summarize_site_batch_wifi_interferences({
            "totalRows": 1, "currentPage": 1, "currentSize": 100,
            "future": True, "data": [{"radioId": 9, "ssid": 7, "new": "x"}],
        })
        self.assertGreater(result["invalid_field_count"], 0)
        self.assertGreater(result["unknown_field_count"], 0)
        self.assertTrue(result["partial"])
        overflow = summarize_site_batch_wifi_interferences({
            "totalRows": 101, "currentPage": 1, "currentSize": 100,
            "data": [_row(i) for i in range(101)],
        })
        self.assertTrue(overflow["data"]["truncated"])
        self.assertEqual(overflow["data"]["processed_interference_count"], 100)

    def test_rejects_invalid_envelopes_and_rows(self):
        for value in (None, [], {"data": {}}):
            with self.subTest(value=value), self.assertRaises(
                    SiteBatchWifiInterferenceSummaryError):
                summarize_site_batch_wifi_interferences(value)


if __name__ == "__main__":
    unittest.main()
