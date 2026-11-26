"""Synthetic coverage tests for site_rate_limit_profiles_summary."""
import unittest

from app.site_rate_limit_profiles_summary import (
    SiteRateLimitProfilesError, summarize_site_rate_limit_profiles,
)
from app.site_hotspot_rate_limit_profiles_summary import (
    SiteHotspotRateLimitProfilesError, summarize_hotspot_rate_limit_profiles,
)


class SiteRateLimitProfilesSummaryTests(unittest.TestCase):
    def test_site_profiles_aggregate_enabled_int64_kbps_only(self):
        result = summarize_site_rate_limit_profiles([
            {"profileId": "PROFILE-ID-PRIVATE", "name": "PROFILE-NAME-PRIVATE",
             "downLimitEnable": True, "downLimit": 20_000_000,
             "upLimitEnable": False, "upLimit": 99_000_000,
             "defaultProfile": True, "resource": 0},
            {"downLimitEnable": False, "downLimit": 80_000_000,
             "upLimitEnable": True, "upLimit": 3_000_000,
             "defaultProfile": False},
        ])
        self.assertEqual(result["profile_count"], 2)
        self.assertFalse(result["empty"])
        down = result["directional_coverage"]["downstream"]
        self.assertEqual(down["enable_counts"], {
            "enabled": 1, "disabled": 1, "missing": 0, "invalid": 0,
        })
        self.assertEqual(down["enabled_limit_coverage"], {
            "reported": 1, "valid": 1, "missing": 0, "invalid": 0,
        })
        self.assertEqual(down["enabled_limit_kbps"], {
            "count": 1, "sum": 20_000_000, "min": 20_000_000, "max": 20_000_000,
        })
        up = result["directional_coverage"]["upstream"]
        self.assertEqual(up["enable_counts"], {
            "enabled": 1, "disabled": 1, "missing": 0, "invalid": 0,
        })
        self.assertEqual(up["enabled_limit_kbps"], {
            "count": 1, "sum": 3_000_000, "min": 3_000_000, "max": 3_000_000,
        })
        self.assertEqual(result["default_profile_counts"], {
            "true": 1, "false": 1, "missing": 0, "invalid": 0,
        })
        self.assertFalse(result["partial"])
        for private in ("PROFILE-ID-PRIVATE", "PROFILE-NAME-PRIVATE", "downLimit",
                        "upLimit", "resource"):
            self.assertNotIn(private, repr(result))

    def test_int64_range_is_route_specific_and_not_hotspot_maximum(self):
        value_above_hotspot_max = 10_485_761
        site_result = summarize_site_rate_limit_profiles([{
            "downLimitEnable": True, "downLimit": value_above_hotspot_max,
            "upLimitEnable": False, "defaultProfile": True,
        }])
        self.assertEqual(
            site_result["directional_coverage"]["downstream"]["enabled_limit_kbps"]["sum"],
            value_above_hotspot_max)
        hotspot_result = summarize_hotspot_rate_limit_profiles([{
            "downLimitEnable": True, "downLimit": value_above_hotspot_max,
            "upLimitEnable": False, "isDefault": True,
        }])
        hotspot_down = hotspot_result["directional_coverage"]["downstream"]
        self.assertEqual(hotspot_down["enabled_limit_coverage"]["invalid"], 1)
        self.assertEqual(hotspot_down["enabled_limit_kbps"]["count"], 0)

        int64_max = (1 << 63) - 1
        int64_min = -(1 << 63)
        boundaries = summarize_site_rate_limit_profiles([
            {"downLimitEnable": True, "downLimit": int64_min,
             "upLimitEnable": False, "defaultProfile": True},
            {"downLimitEnable": True, "downLimit": int64_max,
             "upLimitEnable": False, "defaultProfile": False},
        ])
        agg = boundaries["directional_coverage"]["downstream"]["enabled_limit_kbps"]
        self.assertEqual(agg["min"], int64_min)
        self.assertEqual(agg["max"], int64_max)
        self.assertEqual(agg["count"], 2)

    def test_missing_invalid_disabled_and_default_coverage_are_distinct(self):
        result = summarize_site_rate_limit_profiles([
            {"downLimitEnable": True, "upLimitEnable": True,
             "upLimit": None, "defaultProfile": None},
            {"downLimitEnable": False, "downLimit": 42,
             "upLimitEnable": 1, "isDefault": True},
            {"downLimitEnable": True, "downLimit": 1 << 63,
             "upLimitEnable": False},
            {"upLimitEnable": True, "upLimit": 500},
        ])
        down = result["directional_coverage"]["downstream"]
        self.assertEqual(down["enable_counts"], {
            "enabled": 2, "disabled": 1, "missing": 1, "invalid": 0,
        })
        self.assertEqual(down["enabled_limit_coverage"], {
            "reported": 1, "valid": 0, "missing": 1, "invalid": 1,
        })
        up = result["directional_coverage"]["upstream"]
        self.assertEqual(up["enable_counts"]["invalid"], 1)
        self.assertEqual(up["enabled_limit_coverage"]["invalid"], 1)
        self.assertEqual(result["default_profile_counts"], {
            "true": 0, "false": 0, "missing": 3, "invalid": 1,
        })
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])

    def test_valid_empty_and_malformed_or_over_bound_are_distinct(self):
        empty = summarize_site_rate_limit_profiles([])
        self.assertEqual(empty["profile_count"], 0)
        self.assertTrue(empty["empty"])
        self.assertFalse(empty["partial"])
        for rows in (None, {}, [None] * 1001):
            with self.subTest(kind=type(rows).__name__):
                with self.assertRaises(SiteRateLimitProfilesError):
                    summarize_site_rate_limit_profiles(rows)
        malformed_row = summarize_site_rate_limit_profiles([{"x%d" % i: i for i in range(33)}])
        self.assertEqual(malformed_row["invalid_profile_count"], 1)
        self.assertTrue(malformed_row["partial"])


if __name__ == "__main__":
    unittest.main()
