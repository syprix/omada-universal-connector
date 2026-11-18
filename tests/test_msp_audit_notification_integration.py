import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class MspAuditNotificationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_msp_route_and_redacted_projection(self):
        raw = {"webhookConfig": {"webhookEnable": True, "webhookId": "secret-id"},
               "auditLogNotifications": [{"key": "login", "shortMsg": "Private label",
                                           "webhook": True}]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_msp_audit_notification("msp-1")
        request.assert_called_once_with(
            "GET", "/openapi/v1/msp/msp-1/audit-notification", token="token")
        self.assertEqual(result["resource"], "msp_audit_notification")
        self.assertEqual(result["data"]["enabled_category_count"], 1)
        self.assertNotIn("secret-id", str(result))
        self.assertNotIn("Private label", str(result))
        self.assertFalse(result["partial"])

    def test_bad_msp_reference_and_result_are_rejected(self):
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client.read_msp_audit_notification("../msp")
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_msp_audit_notification("msp-1")


if __name__ == "__main__":
    unittest.main()
