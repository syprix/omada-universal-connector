import unittest

from app.site_gateway_webfilter_summary import summarize_gateway_webfilter_result


class GatewayWebfilterSummaryTests(unittest.TestCase):
    def test_counts_rule_type_status_and_documented_flags_only(self):
        result = summarize_gateway_webfilter_result({
            "totalRows": 2,
            "data": [
                {"id": "private-id", "name": "private-name", "type": "gateway",
                 "status": True, "policy": 0, "sourceIds": ["private-source"],
                 "urls": ["private-url"], "keywords": ["private-keyword"],
                 "timeRange": "private-schedule", "existKeyword": True,
                 "existCategory": False, "existTimeSchedule": True},
                {"type": "ap", "status": False, "existKeyword": False,
                 "existCategory": True, "existTimeSchedule": False},
            ],
            "supportKeyword": True, "supportCategory": False,
            "supportTimeSchedule": True,
        })
        self.assertEqual(result["by_documented_rule_type"], {"ap": 1, "gateway": 1})
        self.assertEqual(result["enabled_status_count"], 1)
        self.assertEqual(result["disabled_status_count"], 1)
        self.assertEqual(result["rule_feature_flag_coverage"]["existKeyword"], {
            "enabled": 1, "disabled": 1, "unknown": 0, "missing": 0,
        })
        self.assertEqual(result["source_feature_support"]["supportCategory"], {
            "supported": 0, "unsupported": 1, "unknown": 0, "missing": 0,
        })
        self.assertFalse(result["partial"])
        for private_value in ("private-id", "private-name", "private-source",
                              "private-url", "private-keyword", "private-schedule"):
            self.assertNotIn(private_value, repr(result))

    def test_unknown_missing_and_truncation_are_reported(self):
        result = summarize_gateway_webfilter_result({
            "totalRows": 4,
            "data": [
                {"type": "future", "status": 1, "existKeyword": None},
                None,
            ],
        }, omitted_rows=1)
        self.assertEqual(result["omitted_rule_count"], 1)
        self.assertEqual(result["unreported_rule_count"], 1)
        self.assertEqual(result["unknown_rule_type_count"], 2)
        self.assertEqual(result["unknown_status_count"], 2)
        self.assertEqual(result["missing_status_count"], 0)
        self.assertTrue(result["partial"])

    def test_rejects_invalid_grid_metadata(self):
        with self.assertRaises(ValueError):
            summarize_gateway_webfilter_result({"totalRows": -1, "data": []})


if __name__ == "__main__":
    unittest.main()
