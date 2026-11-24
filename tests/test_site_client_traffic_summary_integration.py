import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_client_traffic_summary import (
    SiteClientTrafficSummaryError, project_site_client_traffic_summary,
)


def sample_page():
    return {
        "totalRows": 3, "currentPage": 1, "currentSize": 2,
        "data": [
            {"type": "Mobile", "manager": True, "clientName": "private-one",
             "mac": "aa:bb", "traffic": 50, "trafficPercent": {"value": 60},
             "upload": 20, "uploadTrafficPercent": 40, "download": 30,
             "downloadTrafficPercent": 70, "totalApplications": 1,
             "applicationList": [{"applicationName": "private-app", "applicationId": 5,
                 "applicationDescription": "private description", "familyId": 2,
                 "familyName": "private-family", "traffic": 50, "trafficPercent": 100,
                 "clientsCount": 1}], "network": "private-network", "vlanId": "20"},
            {"type": "Wired", "manager": False, "clientName": "private-two",
             "mac": "cc:dd", "traffic": 30, "upload": 15, "download": 15,
             "totalApplications": 1, "applicationList": [{"traffic": 25}],
             "network": "private-network", "vlanId": "20"},
        ],
        "clientTrafficFilters": [{"network": "private-network", "vlanId": "20"}],
    }


class SiteClientTrafficSummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_projector_aggregates_one_page_and_discards_identities(self):
        result = project_site_client_traffic_summary(sample_page(), 0, 2)
        data = result["data"]
        self.assertEqual(data["total_rows"], 3)
        self.assertEqual(data["returned_client_count"], 2)
        self.assertTrue(data["has_more_pages"])
        self.assertEqual(data["client_traffic_total"], 80)
        self.assertEqual(data["client_traffic_peak_per_client"], 50)
        self.assertEqual(data["upload_traffic_total"], 35)
        self.assertEqual(data["download_traffic_total"], 45)
        self.assertEqual(data["application_count_total"], 2)
        self.assertEqual(data["application_detail_row_count"], 2)
        self.assertEqual(data["application_detail_traffic_total"], 75)
        self.assertTrue(result["partial"])
        for private in ("private-one", "aa:bb", "private-app", "private description",
                        "private-family", "private-network"):
            self.assertNotIn(private, repr(result))

    def test_complete_page_is_not_partial_and_percentage_types_are_ignored(self):
        page = sample_page()
        page["totalRows"] = 2
        result = project_site_client_traffic_summary(page, 0, 2)
        self.assertFalse(result["partial"])
        self.assertEqual(result["unknown_field_count"], 0)

    def test_projector_requires_controller_page_number_to_be_one_based(self):
        page = sample_page()
        page["currentPage"] = 0
        result = project_site_client_traffic_summary(page, 0, 2)
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 1)

    def test_projector_rejects_oversize_rows_and_invalid_page_arguments(self):
        with self.assertRaises(SiteClientTrafficSummaryError):
            project_site_client_traffic_summary({"data": [{}] * 101}, 0, 100)
        with self.assertRaises(SiteClientTrafficSummaryError):
            project_site_client_traffic_summary({}, -1, 10)
        with self.assertRaises(SiteClientTrafficSummaryError):
            project_site_client_traffic_summary({}, 0, 101)

    def test_reads_fixed_window_and_selected_bounded_page(self):
        site_ref = "c" * 24
        def request(_method, path, token):
            self.assertTrue(self.client._site_client_traffic_request_valid(path))
            self.assertIn("&page=3&pageSize=50", path)
            return {"result": {"totalRows": 101, "currentPage": 3, "currentSize": 1,
                                "data": [sample_page()["data"][0]]}}
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request) as req:
            result = self.client.read_site_client_traffic_summary(site_ref, 2, 50)
        req.assert_called_once()
        self.assertEqual(result["data"]["returned_client_count"], 1)
        self.assertFalse(result["data"]["has_more_pages"])

    def test_path_guard_binds_controller_window_and_page_bounds(self):
        good = ("/openapi/v1/ctrl/sites/site/dashboard/clientTraffic"
                "?start=100&end=86500&page=1&pageSize=100")
        self.assertTrue(self.client._site_client_traffic_request_valid(good))
        self.assertFalse(self.client._site_client_traffic_request_valid(
            good.replace("page=1", "page=0")))
        self.assertFalse(self.client._site_client_traffic_request_valid(
            good.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_client_traffic_request_valid(
            good.replace("end=86500", "end=86501")))
        self.assertFalse(self.client._site_client_traffic_request_valid(
            good.replace("pageSize=100", "pageSize=101")))
        self.assertTrue(self.client._site_client_traffic_request_valid(
            good.replace("page=1", "page=10001")))
        self.assertFalse(self.client._site_client_traffic_request_valid(
            good.replace("page=1", "page=10002")))

    def test_bad_upstream_page_is_rejected(self):
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaises(OpenApiError):
                self.client.read_site_client_traffic_summary("c" * 24, 0, 10)


if __name__ == "__main__":
    unittest.main()
