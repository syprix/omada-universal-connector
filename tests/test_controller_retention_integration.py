import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerRetentionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_route_and_projected_settings(self):
        raw = {"clientsDataEnable": True, "clientDataTrendEnable": False,
               "knownClient": 31, "knownClientAvailableRetentionDays": [1, 7, 31, 90]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_controller_retention()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/controller/setting/retention", token="token")
        self.assertEqual(result["resource"], "controller_retention")
        self.assertTrue(result["data"]["flags"]["clients_data_enable"])
        self.assertEqual(result["data"]["retention_values"]["known_client"], 31)
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "controller_retention")["runtime_evidence"][0]
        self.assertFalse(evidence["controller_response_observed"])
        self.assertEqual(evidence["permission_state"], "unknown")
        self.assertEqual(evidence["support_state"], "unknown")

    def test_invalid_result_shape_and_controller_mismatch_are_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_retention()
        good = "/openapi/v1/ctrl/controller/setting/retention"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))


if __name__ == "__main__":
    unittest.main()
