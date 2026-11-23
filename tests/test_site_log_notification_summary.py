import unittest

from app.site_log_notification_summary import (
    SiteLogNotificationSummaryError, summarize_site_log_notifications,
)


def settings(**overrides):
    value = {
        "webhookConfig": {"webhookEnable": True, "webhookId": "secret-webhook"},
        "logNotifications": [
            {"key": "LOGIN_OK", "shortMsg": "User Logged In", "alert": False,
             "event": True, "email": True, "webhook": False},
            {"key": "DEVICE_DOWN", "shortMsg": "Private event text", "alert": True,
             "event": True, "email": False, "webhook": True},
        ],
        "alertEmailSetting": {"alertEmailEnable": True, "delayEnable": False,
                              "delay": 30},
    }
    value.update(overrides)
    return value


class SiteLogNotificationSummaryTests(unittest.TestCase):
    def test_counts_switches_and_categories_without_raw_values(self):
        result = summarize_site_log_notifications(settings())
        self.assertEqual(result["notification_category_count"], 2)
        self.assertEqual(result["channel_enablement_counts"]["event"], {
            "enabled": 2, "disabled": 0, "unknown": 0})
        self.assertEqual(result["channel_enablement_counts"]["email"], {
            "enabled": 1, "disabled": 1, "unknown": 0})
        self.assertEqual(result["webhook_master_enablement_counts"]["enabled"], 1)
        self.assertEqual(result["email_setting_enablement_counts"]["alert_email"]["enabled"], 1)
        self.assertEqual(result["email_delay_value_presence"]["present"], 1)
        self.assertFalse(result["partial"])
        for secret in ("LOGIN_OK", "DEVICE_DOWN", "User Logged In", "Private event text",
                       "secret-webhook", "30"):
            self.assertNotIn(secret, str(result))
        self.assertFalse(result["external_destination_or_delivery_inferred"])

    def test_missing_fields_unknown_flags_and_unknown_properties_mark_partial(self):
        result = summarize_site_log_notifications({
            "webhookConfig": {"webhookEnable": None},
            "logNotifications": [{"key": "CUSTOM", "extra": "ignored"}],
            "alertEmailSetting": {"alertEmailEnable": False},
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["channel_enablement_counts"]["alert"]["unknown"], 1)
        self.assertEqual(result["webhook_master_enablement_counts"]["unknown"], 1)

    def test_controller_notification_collections_are_projected_without_labels(self):
        result = summarize_site_log_notifications({
            "webhookConfig": {"webhookEnable": False},
            "alertNotifications": [{"key": "PRIVATE_ALERT", "shortMsg": "private",
                                    "enable": True, "email": False, "webhook": True}],
            "eventNotifications": [{"key": "PRIVATE_EVENT", "shortMsg": "private",
                                    "enable": False, "email": True, "webhook": False}],
            "alertEmailSetting": {"alertEmailEnable": True, "delayEnable": False,
                                  "delay": 20},
            "eventEmailSetting": {"alertEmailEnable": False, "delayEnable": True,
                                  "delay": 10},
        })
        self.assertEqual(result["notification_category_count"], 2)
        self.assertEqual(result["channel_enablement_counts"]["alert"]["enabled"], 1)
        self.assertEqual(result["channel_enablement_counts"]["event"]["disabled"], 1)
        self.assertEqual(result["channel_enablement_counts"]["email"]["enabled"], 1)
        self.assertEqual(result["channel_enablement_counts"]["webhook"]["enabled"], 1)
        self.assertEqual(result["email_setting_enablement_counts"]["event_email"]["disabled"], 1)
        self.assertEqual(result["email_delay_value_presence"]["present"], 2)
        self.assertFalse(result["partial"])
        self.assertNotIn("PRIVATE_ALERT", str(result))
        self.assertNotIn("PRIVATE_EVENT", str(result))

    def test_rejects_invalid_documented_types(self):
        for data in (settings(logNotifications="invalid"),
                     settings(webhookConfig={"webhookEnable": 1}),
                     settings(alertEmailSetting={"delayEnable": False, "delay": -1}),
                     settings(logNotifications=[{"key": 5}])):
            with self.subTest(data=data), self.assertRaises(SiteLogNotificationSummaryError):
                summarize_site_log_notifications(data)


if __name__ == "__main__":
    unittest.main()
