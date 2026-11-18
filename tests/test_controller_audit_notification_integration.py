import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerAuditNotificationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_route_and_redacted_projection(self):
        raw = {"webhookConfig": {"webhookEnable": True, "webhookId": "secret-id"},
               "auditLogNotifications": [{"key": "login", "shortMsg": "Private label",
                                           "webhook": True}]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_controller_audit_notification()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/audit-notification", token="token")
        self.assertEqual(result["resource"], "controller_audit_notification")
        self.assertEqual(result["data"]["enabled_category_count"], 1)
        self.assertNotIn("secret-id", str(result))
        self.assertNotIn("Private label", str(result))
        self.assertFalse(result["partial"])

    def test_invalid_result_and_controller_mismatch_are_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_audit_notification()
        good = "/openapi/v1/ctrl/audit-notification"
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))


if __name__ == "__main__":
    unittest.main()
