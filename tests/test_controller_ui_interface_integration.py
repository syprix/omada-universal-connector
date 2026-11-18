import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerUiInterfaceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_exact_route_redacts_url_file_id_and_filename(self):
        raw = {"timeZone": 1, "refreshRate": 2, "macFormat": 0,
               "privateLabelingEnable": True, "privateLabelingUrl": "https://private.invalid/logo",
               "privateLabelingFileId": "private-file-id", "privateLabelingFileName": "private-name.png"}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_controller_ui_interface()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/controller/setting/ui-interface", token="token")
        self.assertEqual(result["resource"], "controller_ui_interface")
        self.assertEqual(result["data"]["settings"], {
            "time_zone_code": 1, "refresh_rate_code": 2, "mac_format_code": 0,
            "private_labeling_enabled": True})
        self.assertEqual(result["data"]["redacted_field_count"], 3)
        for private in ("https://private.invalid/logo", "private-file-id", "private-name.png"):
            self.assertNotIn(private, str(result))
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "controller_ui_interface")["runtime_evidence"][0]
        self.assertFalse(evidence["controller_response_observed"])
        self.assertEqual(evidence["permission_state"], "unknown")
        self.assertEqual(evidence["support_state"], "unknown")

    def test_wrong_result_shape_and_controller_mismatch_are_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_ui_interface()
        good = "/openapi/v1/ctrl/controller/setting/ui-interface"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))


if __name__ == "__main__":
    unittest.main()
