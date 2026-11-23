import unittest
from unittest.mock import patch
from app.openapi import OmadaOpenApiClient, OpenApiConfig

from app.controller_global_log_notification_summary import (
    ControllerGlobalLogNotificationError, summarize_controller_log_notifications,
)


class ControllerGlobalLogNotificationSummaryTests(unittest.TestCase):
    def test_counts_documented_switches_without_categories_or_destinations(self):
        result = summarize_controller_log_notifications({
            "webhookConfig": {"webhookEnable": True, "webhookId": "secret"},
            "logNotifications": [
                {"key": "LOGIN_OK", "shortMsg": "private message",
                 "alert": False, "event": True, "email": False, "webhook": True},
                {"key": "ANOTHER", "alert": True, "event": True,
                 "email": True, "webhook": False},
            ],
            "alertEmailSetting": {"alertEmailEnable": True,
                                  "delayEnable": False, "delay": 30},
        })
        self.assertEqual(result["notification_category_count"], 2)
        self.assertEqual(result["channel_switch_counts"]["email"],
                         {"enabled": 1, "disabled": 1, "missing": 0})
        self.assertTrue(result["webhook_enabled"])
        self.assertTrue(result["alert_email_enabled"])
        self.assertTrue(result["alert_email_delay_value_present"])
        self.assertNotIn("key", str(result))
        self.assertNotIn("secret", str(result))
        self.assertNotIn("private message", str(result))

    def test_missing_and_unexpected_fields_are_partial(self):
        result = summarize_controller_log_notifications({
            "logNotifications": [{"event": True, "email": "yes", "extra": 1}],
        })
        self.assertTrue(result["partial"])
        self.assertGreater(result["missing_channel_value_count"], 0)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["invalid_field_count"], 1)
        with self.assertRaises(ControllerGlobalLogNotificationError):
            summarize_controller_log_notifications({"logNotifications": {}})

    def test_adapter_uses_only_controller_scoped_read(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "webhookConfig": {"webhookEnable": False},
                    "logNotifications": [],
                    "alertEmailSetting": {"alertEmailEnable": True},
                }}) as request:
            result = client.read_controller_global_log_notification_summary()
        request.assert_called_once_with(
            "GET", "/openapi/v2/ctrl/log-notification", token="token")
        self.assertEqual(result["resource"], "controller_global_log_notification_summary")
        self.assertTrue(client._controller_global_log_notification_request_valid(
            "/openapi/v2/ctrl/log-notification"))
        self.assertFalse(client._controller_global_log_notification_request_valid(
            "/openapi/v2/other/log-notification"))


if __name__ == "__main__":
    unittest.main()
