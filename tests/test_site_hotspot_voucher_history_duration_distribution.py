from __future__ import annotations

import json
import unittest

from app.site_hotspot_voucher_history_duration_distribution import (
    MAX_VOUCHER_DURATION_DISTRIBUTION_ROWS,
    VoucherDurationDistributionError,
    MISSING_VOUCHER_DURATION_DISTRIBUTION_RESULT,
    project_voucher_duration_distribution,
)


class VoucherDurationDistributionProjectionTests(unittest.TestCase):
    def test_missing_null_zero_empty_and_valid_grid_are_distinct(self):
        missing = project_voucher_duration_distribution(
            MISSING_VOUCHER_DURATION_DISTRIBUTION_RESULT)
        null = project_voucher_duration_distribution(None)
        zero = project_voucher_duration_distribution({
            "totalRows": 0, "currentPage": 0, "currentSize": 0, "data": []})
        self.assertEqual(missing["source_state"], "result_missing")
        self.assertEqual(null["source_state"], "result_null")
        self.assertEqual(zero["source_state"], "grid")
        self.assertEqual(zero["grid_field_coverage"]["totalRows"]["zero_count"], 1)
        self.assertEqual(zero["row_count"], 0)
        self.assertFalse(zero["partial"])
        self.assertEqual(zero["server_completeness"], "not_asserted")
        self.assertNotIn("total_rows", zero)

    def test_rows_report_only_bounded_type_and_field_coverage(self):
        raw = {"totalRows": 900, "currentPage": 27, "currentSize": 19,
               "data": [{"duration": 30, "durationType": 0,
                         "totalDuration": 180, "usedCount": 4,
                         "secretLabel": "private-label"},
                        {"duration": None, "durationType": 7,
                         "totalDuration": "private-number", "usedCount": True}]}
        result = project_voucher_duration_distribution(raw)
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["row_field_coverage"]["durationType"], {
            "present": 2, "type_valid": 1, "missing": 0, "null": 0,
            "invalid": 1, "zero_count": 1})
        self.assertEqual(result["row_field_coverage"]["duration"]["null"], 1)
        self.assertEqual(result["row_field_coverage"]["usedCount"]["invalid"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        encoded = json.dumps(result)
        for secret in ("private-label", "private-number", '"duration": 30',
                       '"totalRows": 900', '"currentPage": 27'):
            self.assertNotIn(secret, encoded)
        self.assertEqual(result["server_completeness"], "not_asserted")

    def test_metadata_are_coverage_only_and_do_not_assert_page_completeness(self):
        result = project_voucher_duration_distribution({
            "totalRows": 12, "currentPage": 4, "currentSize": 1,
            "data": [{"duration": 10, "durationType": 1,
                      "totalDuration": 20, "usedCount": 1}]})
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["grid_field_coverage"]["currentPage"]["type_valid"], 1)
        self.assertFalse(result["partial"])
        self.assertEqual(result["server_completeness"], "not_asserted")
        self.assertNotIn("page_number", result)
        self.assertNotIn("reported_total_row_count", result)

    def test_missing_null_invalid_and_unknown_fields_are_counted_without_values(self):
        result = project_voucher_duration_distribution({
            "totalRows": None, "data": [{"durationType": None, "extra": "secret"}]})
        self.assertEqual(result["grid_field_coverage"]["totalRows"]["null"], 1)
        self.assertEqual(result["grid_field_coverage"]["currentPage"]["missing"], 1)
        self.assertEqual(result["row_field_coverage"]["durationType"]["null"], 1)
        self.assertEqual(result["row_field_coverage"]["duration"]["missing"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("secret", json.dumps(result))

    def test_invalid_grid_and_row_limit_are_rejected(self):
        invalid_grid = project_voucher_duration_distribution({"data": {}})
        self.assertEqual(invalid_grid["grid_field_coverage"]["data"]["invalid"], 1)
        self.assertIsNone(invalid_grid["row_count"])
        self.assertTrue(invalid_grid["partial"])
        with self.assertRaises(VoucherDurationDistributionError):
            project_voucher_duration_distribution({
                "data": [{}] * (MAX_VOUCHER_DURATION_DISTRIBUTION_ROWS + 1)})


if __name__ == "__main__":
    unittest.main()
