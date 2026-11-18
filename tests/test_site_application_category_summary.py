import unittest

from app.site_application_category_summary import (
    SiteApplicationCategorySummaryError, project_site_application_category_summary,
)


class SiteApplicationCategorySummaryTests(unittest.TestCase):
    def test_projects_page_counts_and_traffic_without_category_or_client_details(self):
        result = project_site_application_category_summary({
            "totalRows": 123, "currentPage": 1, "currentSize": 2,
            "data": [
                {"familyId": 7, "familyName": "private-category", "traffic": 100,
                 "upload": 40, "download": 60, "trafficPercent": 55.0,
                 "totalApplications": 2, "applications": [{"id": "private-app"}],
                 "totalClients": 3, "clients": [{"mac": "private-mac"}]},
                {"familyName": "another-private-category", "traffic": 50,
                 "trafficPercent": 65.0},
            ],
            "stat": {"allowApps": 10, "blockApps": 4},
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["category_row_count"], 2)
        self.assertEqual(result["data"]["total_category_count"], 123)
        self.assertEqual(result["data"]["page_traffic_total_value"], 150)
        self.assertEqual(result["data"]["maximum_category_traffic_share_percent"], 65.0)
        self.assertEqual(result["data"]["unseen_category_row_count"], 121)
        for value in ("private-category", "another-private-category", "private-app", "private-mac"):
            self.assertNotIn(value, repr(result))

    def test_complete_page_is_full_and_counts_redacted_nested_rows(self):
        result = project_site_application_category_summary({
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
            "data": [{"familyId": 2, "familyName": "hidden", "traffic": 70,
                      "upload": 20, "download": 50, "trafficPercent": 100,
                      "totalApplications": 1, "applications": [{"applicationName": "hidden-app"}],
                      "totalClients": 1, "clients": [{"clientName": "hidden-client"}]}],
            "stat": {"allowApps": 1, "blockApps": 0},
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["category_rows_with_applications"], 1)
        self.assertEqual(result["data"]["category_rows_with_clients"], 1)
        for value in ("hidden", "hidden-app", "hidden-client"):
            self.assertNotIn(value, repr(result))

    def test_flags_unknown_and_invalid_fields_and_bounds_page(self):
        result = project_site_application_category_summary({
            "totalRows": 1, "currentPage": 0, "currentSize": 1,
            "data": [{"traffic": -1, "familyName": 3, "future": "hidden"}],
            "stat": {"allowApps": -1}, "futureRoot": True,
        })
        self.assertTrue(result["partial"])
        self.assertGreaterEqual(result["invalid_field_count"], 3)
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertNotIn("hidden", repr(result))
        with self.assertRaises(SiteApplicationCategorySummaryError):
            project_site_application_category_summary({"data": [{}] * 101})
        with self.assertRaises(SiteApplicationCategorySummaryError):
            project_site_application_category_summary([])


if __name__ == "__main__":
    unittest.main()
