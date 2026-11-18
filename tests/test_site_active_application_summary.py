import unittest

from app.site_active_application_summary import (
    SiteActiveApplicationSummaryError, project_site_active_application_summary,
)


class SiteActiveApplicationSummaryTests(unittest.TestCase):
    def test_projects_application_totals_without_names_or_identifiers(self):
        result = project_site_active_application_summary([
            {"applicationName": "hidden-one", "applicationId": 1,
             "applicationDescription": "private description", "familyId": 2,
             "familyName": "private category", "traffic": 90,
             "trafficPercent": 60, "clientsCount": 4},
            {"applicationName": "hidden-two", "applicationId": 3,
             "applicationDescription": "private description", "familyId": 2,
             "familyName": "private category", "traffic": 50,
             "trafficPercent": 40, "clientsCount": 2},
        ])
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["application_count"], 2)
        self.assertEqual(result["data"]["total_application_traffic_value"], 140)
        self.assertEqual(result["data"]["maximum_application_traffic_value"], 90)
        self.assertEqual(result["data"]["total_client_application_count"], 6)
        for value in ("hidden-one", "hidden-two", "private description", "private category"):
            self.assertNotIn(value, repr(result))

    def test_marks_missing_invalid_unknown_and_mismatched_percentage_partial(self):
        result = project_site_active_application_summary([
            {"traffic": 5, "clientsCount": -1,
             "trafficPercent": {"value": 50}, "future": "omitted"},
            {"traffic": 10, "clientsCount": 1},
        ])
        self.assertTrue(result["partial"])
        self.assertGreaterEqual(result["data"]["missing_field_count"], 1)
        self.assertGreaterEqual(result["data"]["invalid_field_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("omitted", repr(result))

    def test_rejects_malformed_or_overlarge_result(self):
        with self.assertRaises(SiteActiveApplicationSummaryError):
            project_site_active_application_summary({"data": []})
        with self.assertRaises(SiteActiveApplicationSummaryError):
            project_site_active_application_summary([{}] * 1_001)


if __name__ == "__main__":
    unittest.main()
