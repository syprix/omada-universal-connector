import unittest

from app.site_batch_interference_status_summary import (
    summarize_site_batch_interference_status,
)


class SiteBatchInterferenceStatusSummaryTests(unittest.TestCase):
    def test_projects_documented_status_and_omits_raw_history_id(self):
        result = summarize_site_batch_interference_status(
            [{"historyId": "opaque-source-id", "status": 1}],
            expected_history_id="opaque-source-id")
        self.assertEqual(result["data"]["items"], [{"status": "scanning"}])
        self.assertFalse(result["partial"])
        self.assertNotIn("opaque-source-id", repr(result))

    def test_unknown_or_mismatched_rows_are_omitted_and_mark_partial(self):
        result = summarize_site_batch_interference_status(
            [{"historyId": "other", "status": 0},
             {"historyId": "selected", "status": 2}],
            expected_history_id="selected")
        self.assertEqual(result["data"]["items"], [])
        self.assertEqual(result["data"]["invalid_value_count"], 3)
        self.assertTrue(result["partial"])

    def test_unknown_fields_are_counted(self):
        result = summarize_site_batch_interference_status(
            [{"historyId": "selected", "status": 0, "mac": "private"}],
            expected_history_id="selected")
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))


if __name__ == "__main__":
    unittest.main()
