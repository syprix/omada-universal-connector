from __future__ import annotations

import unittest

from app.site_voucher_all_time_summary import summarize_all_time_vouchers


class SiteVoucherAllTimeSummaryTests(unittest.TestCase):
    def test_projects_each_documented_category_without_amount_or_currency_values(self):
        raw = {
            category: {"count": index + 1, "amount": f"revenue-secret-{index}",
                       "duration": (index + 1) * 60, "currency": "USD"}
            for index, category in enumerate(("current", "inuse", "expired", "unused", "created"))
        }
        raw["supportVoucherTrafficStat"] = True
        result = summarize_all_time_vouchers(raw)
        self.assertFalse(result["partial"])
        self.assertEqual(result["voucher_counts"]["current"], 1)
        self.assertEqual(result["voucher_durations_minutes"]["created"], 300)
        self.assertEqual(result["voucher_traffic_statistics_supported"], True)
        serialized = str(result)
        for secret in ("revenue-secret", "USD"):
            self.assertNotIn(secret, serialized)

    def test_marks_missing_category_fields_individually(self):
        result = summarize_all_time_vouchers({"current": {"count": 0}})
        self.assertTrue(result["partial"])
        self.assertEqual(result["voucher_counts"]["current"], 0)
        self.assertIsNone(result["voucher_durations_minutes"]["current"])
        self.assertNotIn("current.count", result["missing_fields"])
        self.assertIn("current.duration", result["missing_fields"])
        self.assertIn("unused.count", result["missing_fields"])
        self.assertIn("supportVoucherTrafficStat", result["missing_fields"])

    def test_invalid_values_and_unknown_categories_are_partial(self):
        result = summarize_all_time_vouchers({"current": {"count": -1, "extra": 1},
                                              "vendorField": "ignored"})
        self.assertTrue(result["partial"])
        self.assertIsNone(result["voucher_counts"]["current"])
        self.assertIn("current.count", result["invalid_fields"])
        self.assertGreaterEqual(result["unknown_field_count"], 2)


if __name__ == "__main__":
    unittest.main()
