import unittest

from app.site_top_ap_retry_drop_summary import (
    SiteTopApRetryDropSummaryError, project_site_top_ap_retry_drop_summary,
)


class SiteTopApRetryDropSummaryTests(unittest.TestCase):
    def test_projects_bounded_counts_and_maximum_ratios_without_device_data(self):
        payload = {"topApByRt": [{"device": "private-device", "ratio": 11},
                                  {"mac": "private-mac", "ratio": 72}],
                   "topApByDrop": [{"ip": "private-ip", "ratio": 9}]}
        result = project_site_top_ap_retry_drop_summary(payload)
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"], {
            "top_ap_by_rt_count": 2, "maximum_ap_by_rt_ratio_percent": 72,
            "top_ap_by_drop_count": 1, "maximum_ap_by_drop_ratio_percent": 9,
        })
        for value in ("private-device", "private-mac", "private-ip"):
            self.assertNotIn(value, repr(result))

    def test_reports_missing_invalid_and_unknown_fields(self):
        result = project_site_top_ap_retry_drop_summary({
            "topApByRt": [{"ratio": 101, "future": "secret"}],
            "topApByDrop": [], "futureRoot": "hidden",
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertNotIn("secret", repr(result))
        with self.assertRaises(SiteTopApRetryDropSummaryError):
            project_site_top_ap_retry_drop_summary({"topApByRt": [{}] * 6})
        with self.assertRaises(SiteTopApRetryDropSummaryError):
            project_site_top_ap_retry_drop_summary({"topApByRt": {}, "topApByDrop": []})


if __name__ == "__main__":
    unittest.main()
