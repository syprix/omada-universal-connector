import unittest

from app.site_ap_interference_summary import (
    SiteApInterferenceSummaryError, project_site_ap_interference_summary,
)


class SiteApInterferenceSummaryTests(unittest.TestCase):
    def test_projects_band_counts_and_maximum_values_without_ap_details(self):
        result = project_site_ap_interference_summary({
            "apInterference2g": [
                {"name": "private-ap", "mac": "private-mac", "interUtil": 41},
                {"model": "private-model", "interUtil": 72},
            ],
            "apInterference5g": [], "apInterference5g2": [],
            "apInterference6g": [],
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["2g_ap_count"], 2)
        self.assertEqual(result["data"]["2g_maximum_interference_value"], 72)
        self.assertEqual(result["data"]["total_ap_row_count"], 2)
        for value in ("private-ap", "private-mac", "private-model"):
            self.assertNotIn(value, repr(result))

    def test_recursive_schema_shape_is_flagged_partial_and_limits_rows(self):
        result = project_site_ap_interference_summary({
            "apInterference2g": [{"interferences2g": [{"interUtil": 30}]}],
            "apInterference5g": [], "apInterference5g2": [],
            "apInterference6g": [],
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["missing_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        with self.assertRaises(SiteApInterferenceSummaryError):
            project_site_ap_interference_summary({"apInterference2g": [{}] * 6})
        with self.assertRaises(SiteApInterferenceSummaryError):
            project_site_ap_interference_summary({"apInterference2g": {}})


if __name__ == "__main__":
    unittest.main()
