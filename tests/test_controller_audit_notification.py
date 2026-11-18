import unittest

from app.controller_audit_notification import (
    ControllerAuditNotificationError, project_controller_audit_notification,
)


class ControllerAuditNotificationTests(unittest.TestCase):
    def test_projects_counts_and_omits_identifiers_and_labels(self):
        result = project_controller_audit_notification({
            "webhookConfig": {"webhookEnable": True, "webhookId": "secret-id"},
            "auditLogNotifications": [
                {"key": "login", "shortMsg": "Private label", "webhook": True},
                {"key": "config.change", "shortMsg": "Another label", "webhook": False},
            ],
        })
        self.assertEqual(result["data"]["webhook"], {
            "enabled": True, "webhook_id_present": True,
        })
        self.assertEqual(result["data"]["category_count"], 2)
        self.assertEqual(result["data"]["enabled_category_count"], 1)
        self.assertEqual(result["data"]["omitted_label_count"], 2)
        self.assertFalse(result["partial"])
        self.assertNotIn("secret-id", str(result))
        self.assertNotIn("Private label", str(result))
        self.assertNotIn("login", str(result))

    def test_invalid_and_unknown_values_are_partial_and_redacted(self):
        result = project_controller_audit_notification({
            "webhookConfig": {"webhookEnable": 1, "webhookId": "id"},
            "auditLogNotifications": [{"key": "bad key", "webhook": True,
                                       "private": "secret"}],
            "private": "secret",
        })
        self.assertTrue(result["partial"])
        self.assertGreaterEqual(result["data"]["invalid_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 2)
        self.assertNotIn("secret", str(result))
        self.assertNotIn('"id"', str(result))

    def test_rejects_wrong_shape_and_unbounded_object(self):
        for value in (None, [], "bad", {str(i): i for i in range(9)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(
                    ControllerAuditNotificationError):
                project_controller_audit_notification(value)


if __name__ == "__main__":
    unittest.main()
