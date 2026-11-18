from __future__ import annotations

import unittest

from app.site_wifi_summary import SiteWifiSummaryError, project_site_wifi_summary


class SiteWifiSummaryTests(unittest.TestCase):
    def test_projects_documented_summary_fields(self) -> None:
        result = project_site_wifi_summary({
            "connectedApNum": 3, "clients": 17, "channelUtilization": 42,
            "totalTraffic": 1234.5,
        })
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"], {
            "connectedApNum": 3, "clients": 17, "channelUtilization": 42,
            "totalTraffic": 1234.5,
        })

    def test_preserves_documented_null_utilization(self) -> None:
        result = project_site_wifi_summary({
            "connectedApNum": 0, "clients": 0, "channelUtilization": None,
            "totalTraffic": 0,
        })
        self.assertFalse(result["partial"])
        self.assertIsNone(result["data"]["channelUtilization"])

    def test_missing_invalid_and_unknown_values_mark_partial(self) -> None:
        missing = project_site_wifi_summary({})
        self.assertTrue(missing["partial"])
        self.assertEqual(set(missing["missing_fields"]), {
            "connectedApNum", "clients", "channelUtilization", "totalTraffic"})
        invalid = project_site_wifi_summary({
            "connectedApNum": True, "clients": -1, "channelUtilization": 101,
            "totalTraffic": float("inf"), "private": "do-not-return",
        })
        self.assertTrue(invalid["partial"])
        self.assertEqual(set(invalid["invalid_fields"]), {
            "connectedApNum", "clients", "channelUtilization", "totalTraffic"})
        self.assertEqual(invalid["unknown_field_count"], 1)
        self.assertNotIn("do-not-return", repr(invalid))

    def test_rejects_non_object_and_excessive_roots(self) -> None:
        for raw in (None, [], {f"field_{index}": 0 for index in range(17)}):
            with self.subTest(raw=raw), self.assertRaises(SiteWifiSummaryError):
                project_site_wifi_summary(raw)


if __name__ == "__main__":
    unittest.main()
