import unittest

from app.site_category_client_summary import (
    SiteCategoryClientSummaryError, project_site_category_client_summary,
)


class SiteCategoryClientSummaryTests(unittest.TestCase):
    def test_projects_client_aggregates_without_client_or_network_details(self):
        result = project_site_category_client_summary([
            {"type": "wireless", "manager": True, "clientName": "hidden-one",
             "mac": "02:00:00:00:00:01", "traffic": 90, "trafficPercent": 60,
             "upload": 20, "uploadTrafficPercent": 40, "download": 70,
             "downloadTrafficPercent": 70, "totalApplications": 2,
             "applicationList": [{"applicationName": "hidden-app", "applicationId": 7}],
             "network": "hidden-network", "vlanId": "hidden-vlan"},
            {"type": "wired", "manager": False, "clientName": "hidden-two",
             "mac": "02:00:00:00:00:02", "traffic": 40, "trafficPercent": 40,
             "upload": 10, "uploadTrafficPercent": 20, "download": 30,
             "downloadTrafficPercent": 30, "totalApplications": 1,
             "applicationList": []},
        ])
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["client_count"], 2)
        self.assertEqual(result["data"]["total_client_traffic_value"], 130)
        self.assertEqual(result["data"]["maximum_client_traffic_value"], 90)
        self.assertEqual(result["data"]["total_application_count"], 3)
        self.assertEqual(result["data"]["clients_with_application_rows"], 1)
        for value in ("hidden-one", "hidden-two", "02:00:00:00:00:01",
                      "hidden-app", "hidden-network", "hidden-vlan"):
            self.assertNotIn(value, repr(result))

    def test_marks_malformed_and_contract_mismatch_fields_partial(self):
        result = project_site_category_client_summary([
            {"traffic": 5, "trafficPercent": {"value": 50}, "future": "omitted"}
        ])
        self.assertTrue(result["partial"])
        self.assertGreaterEqual(result["data"]["missing_field_count"], 5)
        self.assertGreaterEqual(result["data"]["invalid_field_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("omitted", repr(result))

    def test_rejects_malformed_or_overlarge_result(self):
        with self.assertRaises(SiteCategoryClientSummaryError):
            project_site_category_client_summary({"data": []})
        with self.assertRaises(SiteCategoryClientSummaryError):
            project_site_category_client_summary([{}] * 1_001)


if __name__ == "__main__":
    unittest.main()
