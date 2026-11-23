from __future__ import annotations

import unittest

from app.site_ap_webfilter_summary import summarize_ap_webfilter_rows
from app.site_url_filter_general_summary import summarize_url_filter_general


class SiteWebfilterProjectionTests(unittest.TestCase):
    def test_ap_rules_count_documented_fields_and_discard_rule_values(self):
        result = summarize_ap_webfilter_rows(
            [{"type": "ap", "status": True, "filterMode": 0,
              "existKeyword": False, "existCategory": True,
              "existTimeSchedule": False, "urls": ["private.example"],
              "keywords": ["private"], "categories": [1],
              "timeRange": "private-schedule", "sourceIds": ["private-id"]}],
            1, 0, {"supportKeyword": True, "supportCategory": False,
                   "supportTimeSchedule": True})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["by_documented_endpoint_rule_type"]["ap"], 1)
        self.assertEqual(result["by_documented_ap_filter_mode"]["url"], 1)
        self.assertEqual(result["reported_ap_rule_status"]["enabled"], 1)
        self.assertFalse(result["raw_rules_urls_keywords_categories_schedules_and_sources_returned"])
        self.assertNotIn("private.example", repr(result))
        self.assertNotIn("private-schedule", repr(result))

    def test_ap_unknown_scope_and_truncation_are_partial(self):
        result = summarize_ap_webfilter_rows(
            [{"type": "gateway", "status": False, "filterMode": 1}],
            2, 1, {})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["by_documented_endpoint_rule_type"]["gateway"], 1)
        self.assertEqual(result["reported_ap_rule_status"]["disabled"], 0)

    def test_general_flags_distinguish_false_and_unknown_and_omit_message(self):
        result = summarize_url_filter_general(
            {"safeSearch": True, "blockPage": False,
             "blockPageMessage": "private message"})
        self.assertEqual(result["reported_settings"],
                         {"safeSearch": "enabled", "blockPage": "disabled"})
        self.assertNotIn("private message", repr(result))
        partial = summarize_url_filter_general({"safeSearch": False})
        self.assertEqual(partial["reported_settings"]["safeSearch"], "disabled")
        self.assertEqual(partial["reported_settings"]["blockPage"], "unknown")
        self.assertEqual(partial["status"], "partial")


if __name__ == "__main__":
    unittest.main()
