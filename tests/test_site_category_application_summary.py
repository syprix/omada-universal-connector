import unittest

from app.site_category_application_summary import (
    SiteCategoryApplicationSummaryError,
    project_site_category_application_summary,
)


class SiteCategoryApplicationSummaryTests(unittest.TestCase):
    def test_projects_aggregate_fields_and_omits_application_and_client_details(self):
        result = project_site_category_application_summary([
            {"applicationName": "hidden-one", "applicationId": 1,
             "familyName": "hidden-category", "familyId": 17, "traffic": 90,
             "trafficPercent": 60, "block": 3, "activeUser": 2,
             "download": 70, "upload": 20, "clientsCount": 4,
             "clients": [{"mac": "hidden-mac"}]},
            {"applicationName": "hidden-two", "applicationId": 2,
             "familyName": "hidden-category", "familyId": 17, "traffic": 50,
             "trafficPercent": 40, "block": 1, "activeUser": 1,
             "download": 35, "upload": 15, "clientsCount": 2, "clients": []},
        ])
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["application_count"], 2)
        self.assertEqual(result["data"]["total_application_traffic_value"], 140)
        self.assertEqual(result["data"]["maximum_application_traffic_value"], 90)
        self.assertEqual(result["data"]["block_event_count"], 4)
        self.assertEqual(result["data"]["active_user_count"], 3)
        self.assertEqual(result["data"]["client_application_count"], 6)
        self.assertEqual(result["data"]["applications_with_client_rows"], 1)
        for value in ("hidden-one", "hidden-two", "hidden-category", "hidden-mac"):
            self.assertNotIn(value, repr(result))

    def test_marks_missing_invalid_and_unknown_fields_partial(self):
        result = project_site_category_application_summary([
            {"traffic": -1, "trafficPercent": {"value": 20}, "future": "omitted"}
        ])
        self.assertTrue(result["partial"])
        self.assertGreaterEqual(result["data"]["missing_field_count"], 5)
        self.assertGreaterEqual(result["data"]["invalid_field_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("omitted", repr(result))

    def test_rejects_malformed_or_overlarge_result(self):
        with self.assertRaises(SiteCategoryApplicationSummaryError):
            project_site_category_application_summary({"data": []})
        with self.assertRaises(SiteCategoryApplicationSummaryError):
            project_site_category_application_summary([{}] * 1_001)


if __name__ == "__main__":
    unittest.main()
