from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_anomaly_event_settings import (
    SiteAnomalyEventSettingsError, project_site_anomaly_event_settings,
)


class SiteAnomalyEventSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_projects_event_rows_and_statistics_and_omits_parameter_values(self) -> None:
        private_value = 987654
        result = project_site_anomaly_event_settings({
            "totalRows": 1, "currentPage": 1, "currentSize": 100, "resource": 2,
            "data": [{"anomalyCode": "01001001", "category": 11,
                      "enable": True, "level": 2, "objectType": "gateway",
                      "params": {"offlineCount": private_value}}],
            "statistic": {"all": 1, "enable": 1, "disable": 0, "allLevel": 1,
                          "critical": 0, "error": 0, "warning": 1, "info": 0},
        })
        item = result["data"]["items"][0]
        self.assertEqual(item, {"anomaly_code": "01001001", "category_code": 11,
                                "enabled": True, "level_code": 2, "object_type": "gateway"})
        self.assertNotIn(str(private_value), repr(result))
        self.assertEqual(result["data"]["omitted_parameter_count"], 1)
        self.assertTrue(result["partial"])

    def test_marks_oversized_page_and_counts_unknown_values(self) -> None:
        result = project_site_anomaly_event_settings({
            "totalRows": 125, "data": [
                {"anomalyCode": "01001001", "enable": False, "level": 3,
                 "category": 0, "objectType": "futureType", "privateName": "secret"}
            ],
        })
        self.assertTrue(result["data"]["has_more"])
        self.assertEqual(result["data"]["omitted_row_count"], 124)
        self.assertEqual(result["data"]["unknown_field_count"], 2)
        self.assertNotIn("secret", repr(result))
        self.assertNotIn("futureType", repr(result))
        self.assertTrue(result["partial"])

    def test_rejects_bad_or_oversized_envelopes_and_rows(self) -> None:
        for value in (None, [], {str(i): True for i in range(13)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(
                    SiteAnomalyEventSettingsError):
                project_site_anomaly_event_settings(value)
        result = project_site_anomaly_event_settings({"data": [
            {"anomalyCode": "x"} for _ in range(101)]})
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertEqual(result["data"]["returned_count"], 0)

    def test_reads_fixed_first_page_for_known_site_only(self) -> None:
        payload = {"totalRows": 0, "currentPage": 1, "currentSize": 100,
                   "data": [], "resource": 0}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": payload}) as request:
            result = self.client.read_site_anomaly_event_settings(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/anomaly/setting?page=1&pageSize=100",
            token="token")
        self.assertEqual(result["resource"], "site_anomaly_event_settings")
        self.assertFalse(result["partial"])
        with self.assertRaisesRegex(OpenApiError, "site_ref_invalid"):
            self.client.read_site_anomaly_event_settings("invalid")
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_anomaly_event_settings("b" * 24)

    def test_rejects_unlisted_query_variants_and_bad_upstream_payload(self) -> None:
        good = "/openapi/v1/ctrl/sites/site_1/anomaly/setting?page=1&pageSize=100"
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good + "&filters.enable=0")
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": None}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_anomaly_event_settings(self.site_ref)


if __name__ == "__main__":
    unittest.main()
