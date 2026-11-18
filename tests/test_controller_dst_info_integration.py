import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerDstInfoIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_route_and_projected_dst_settings(self):
        raw = {"enable": False, "status": False, "mode": 0, "offset": 3_600_000,
               "timeZone": "Europe/Berlin"}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_controller_dst_info()
        request.assert_called_once_with("GET", "/openapi/v1/ctrl/dst-info", token="token")
        self.assertEqual(result["resource"], "controller_dst_info")
        self.assertFalse(result["data"]["settings"]["enabled"])
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "controller_dst_info")["runtime_evidence"][0]
        self.assertFalse(evidence["controller_response_observed"])
        self.assertEqual(evidence["support_state"], "unknown")

    def test_invalid_result_shape_and_controller_mismatch_are_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_dst_info()
        good = "/openapi/v1/ctrl/dst-info"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))


if __name__ == "__main__":
    unittest.main()
