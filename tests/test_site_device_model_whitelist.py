"""Synthetic coverage tests for site_device_model_whitelist_coverage."""
import unittest

from app.site_device_model_whitelist import (
    SiteDeviceWhitelistError, summarize_site_device_whitelist,
)


class SiteDeviceModelWhitelistCoverageTests(unittest.TestCase):
    def test_valid_empty_array_is_distinct_and_complete(self):
        result = summarize_site_device_whitelist([])
        self.assertEqual(result["data"], {
            "record_count": 0,
            "empty": True,
            "known_fields_complete_count": 0,
            "model_coverage": {
                "valid_count": 0, "missing_count": 0, "invalid_count": 0,
                "uninspected_record_count": 0,
            },
            "hardware_version_coverage": {
                "valid_count": 0, "missing_count": 0, "invalid_count": 0,
                "uninspected_record_count": 0,
            },
            "unreadable_record_count": 0,
            "unknown_field_count": 0,
            "truncation_status": "not_reported_by_contract",
        })
        self.assertFalse(result["partial"])

    def test_reports_only_counts_for_valid_missing_and_invalid_fields(self):
        result = summarize_site_device_whitelist([
            {"model": "MODEL-PRIVATE", "hwVersion": "VERSION-PRIVATE"},
            {"model": "MODEL-PRIVATE"},
            {"model": None, "hwVersion": 17},
            {"model": "MODEL-PRIVATE", "hwVersion": "VERSION-PRIVATE",
             "future": "IDENTIFIER-PRIVATE"},
            {"hwVersion": "VERSION-PRIVATE"},
        ])
        self.assertEqual(result["data"]["record_count"], 5)
        self.assertFalse(result["data"]["empty"])
        self.assertEqual(result["data"]["known_fields_complete_count"], 2)
        self.assertEqual(result["data"]["model_coverage"], {
            "valid_count": 3, "missing_count": 1, "invalid_count": 1,
            "uninspected_record_count": 0,
        })
        self.assertEqual(result["data"]["hardware_version_coverage"], {
            "valid_count": 3, "missing_count": 1, "invalid_count": 1,
            "uninspected_record_count": 0,
        })
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        for private in ("MODEL-PRIVATE", "VERSION-PRIVATE", "IDENTIFIER-PRIVATE"):
            self.assertNotIn(private, repr(result))

    def test_unreadable_row_is_counted_without_inventing_field_values(self):
        result = summarize_site_device_whitelist([None])
        self.assertEqual(result["data"]["unreadable_record_count"], 1)
        self.assertEqual(result["data"]["model_coverage"]["uninspected_record_count"], 1)
        self.assertEqual(
            result["data"]["hardware_version_coverage"]["uninspected_record_count"], 1)
        self.assertTrue(result["partial"])

    def test_malformed_and_over_bound_responses_fail_closed(self):
        for value in (None, {}, "[]", [None] * 513):
            with self.subTest(value_type=type(value).__name__, length=len(value) if isinstance(value, list) else None):
                with self.assertRaises(SiteDeviceWhitelistError):
                    summarize_site_device_whitelist(value)
        with self.assertRaises(SiteDeviceWhitelistError):
            summarize_site_device_whitelist([{"field_%d" % i: True for i in range(33)}])


if __name__ == "__main__":
    unittest.main()
