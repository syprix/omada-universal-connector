import unittest

from app.site_batch_interference_result_summary import (
    SiteBatchInterferenceResultSummaryError,
    summarize_site_batch_interferences,
)


class SiteBatchInterferenceResultSummaryTests(unittest.TestCase):
    def test_counts_recursive_entries_by_documented_band_without_returning_records(self):
        result = summarize_site_batch_interferences([{
            "interferences2g": [{"interferences5g": [{}]}],
            "interferences5g": [{"interferences6g": []}],
            "interferences6g": [],
        }])
        self.assertEqual(result["data"]["band_entry_counts"],
                         {"2g": 1, "5g": 2, "6g": 0})
        self.assertTrue(result["data"]["coverage_unknown"])
        self.assertTrue(result["partial"])
        self.assertNotIn("interferences2g", repr(result))

    def test_unknown_fields_are_counted_and_mark_partial(self):
        result = summarize_site_batch_interferences([{
            "interferences2g": [], "interferences5g": [], "interferences6g": [],
            "privateMac": "00:11:22:33:44:55"}])
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("00:11:22:33:44:55", repr(result))

    def test_rejects_unbounded_and_malformed_lists(self):
        with self.assertRaises(SiteBatchInterferenceResultSummaryError):
            summarize_site_batch_interferences({})
        with self.assertRaises(SiteBatchInterferenceResultSummaryError):
            summarize_site_batch_interferences([{"interferences2g": "bad"}])
        with self.assertRaises(SiteBatchInterferenceResultSummaryError):
            summarize_site_batch_interferences([{"interferences2g": [{}] * 257}])


if __name__ == "__main__":
    unittest.main()

