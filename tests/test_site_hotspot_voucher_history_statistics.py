from __future__ import annotations

import unittest

from app.site_hotspot_voucher_history_statistics import (
    VoucherHistoryStatisticsError, summarize_voucher_history_statistics,
)


class VoucherHistoryStatisticsTests(unittest.TestCase):
    def test_projects_only_summary_values_and_usage_coverage(self):
        result = summarize_voucher_history_statistics({
            "summary": {"count": 0, "duration": 15, "amount": "private-amount",
                        "currency": "private-currency"},
            "usage": [{"count": 2, "timeInterval": 30, "time": 1700000000000,
                       "amount": "private-row-amount", "currency": "private-row-currency",
                       "privateIdentity": "private-identity"}],
        })
        self.assertEqual(result["voucher_count"], 0)
        self.assertEqual(result["voucher_duration_minutes"], 15)
        self.assertEqual(result["usage_state"], "nonempty")
        self.assertEqual(result["usage_coverage"]["row_count"], 1)
        self.assertEqual(result["usage_coverage"]["fields"]["count"]["valid_type_count"], 1)
        encoded = repr(result)
        for secret in ("private-amount", "private-currency", "1700000000000",
                       "privateIdentity", "private-identity", "30"):
            self.assertNotIn(secret, encoded)

    def test_distinguishes_missing_null_zero_and_empty_usage(self):
        missing = summarize_voucher_history_statistics({"summary": {}})
        null = summarize_voucher_history_statistics({"summary": None, "usage": None})
        empty = summarize_voucher_history_statistics({
            "summary": {"count": 0, "duration": 0}, "usage": []})
        self.assertEqual(missing["usage_state"], "missing")
        self.assertEqual(null["usage_state"], "null")
        self.assertEqual(empty["usage_state"], "empty")
        self.assertEqual(empty["voucher_count"], 0)
        self.assertEqual(empty["voucher_duration_minutes"], 0)
        self.assertFalse(empty["partial"])
        self.assertIsNone(missing["voucher_count"])
        self.assertTrue(missing["partial"])

    def test_missing_or_null_summary_metrics_mark_an_otherwise_complete_window_partial(self):
        missing_count = summarize_voucher_history_statistics({
            "summary": {"duration": 10}, "usage": []})
        null_duration = summarize_voucher_history_statistics({
            "summary": {"count": 1, "duration": None}, "usage": []})
        complete_zero = summarize_voucher_history_statistics({
            "summary": {"count": 0, "duration": 0}, "usage": []})

        self.assertTrue(missing_count["partial"])
        self.assertEqual(missing_count["summary_field_states"]["voucher_count"], "missing")
        self.assertIn("summary.count", missing_count["missing_fields"])
        self.assertTrue(null_duration["partial"])
        self.assertEqual(null_duration["summary_field_states"][
            "voucher_duration_minutes"], "null")
        self.assertIn("summary.duration", null_duration["missing_fields"])
        self.assertFalse(complete_zero["partial"])
        self.assertEqual(complete_zero["voucher_count"], 0)
        self.assertEqual(complete_zero["voucher_duration_minutes"], 0)

    def test_usage_types_and_unknowns_are_counted_without_values_or_keys(self):
        result = summarize_voucher_history_statistics({
            "summary": {"count": True, "duration": -1, "secretSummaryKey": "x"},
            "usage": [{"count": True, "timeInterval": 2**31, "time": None,
                       "secretDynamicKey": "secret"}, "not-a-row"],
        })
        self.assertEqual(result["summary_field_states"], {
            "voucher_count": "invalid", "voucher_duration_minutes": "invalid"})
        self.assertEqual(result["usage_coverage"]["invalid_row_count"], 1)
        self.assertEqual(result["usage_coverage"]["unknown_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("secretDynamicKey", repr(result))
        self.assertTrue(result["partial"])

    def test_signed_documented_usage_integer_fields_are_counted_by_type(self):
        result = summarize_voucher_history_statistics({
            "summary": {"count": 1, "duration": 1},
            "usage": [{"count": 0, "timeInterval": -1, "time": -1}],
        })
        fields = result["usage_coverage"]["fields"]
        self.assertEqual(fields["timeInterval"]["valid_type_count"], 1)
        self.assertEqual(fields["time"]["valid_type_count"], 1)
        self.assertEqual(fields["timeInterval"]["invalid_count"], 0)
        self.assertEqual(fields["time"]["invalid_count"], 0)

    def test_usage_row_limit_is_strict(self):
        with self.assertRaises(VoucherHistoryStatisticsError):
            summarize_voucher_history_statistics({"summary": {}, "usage": [{}] * 501})
        accepted = summarize_voucher_history_statistics({"summary": {}, "usage": [{}] * 500})
        self.assertEqual(accepted["usage_coverage"]["row_count"], 500)


if __name__ == "__main__":
    unittest.main()
