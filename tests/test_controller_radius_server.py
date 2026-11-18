import unittest

from app.controller_radius_server import (
    ControllerRadiusServerError,
    project_controller_radius_server,
)


class ControllerRadiusServerTests(unittest.TestCase):
    def test_projects_settings_and_redacts_sensitive_values(self):
        raw = {
            "enable": True, "authServerPort": 1812, "secret": "radius-private",
            "tunnelReplyEnable": False, "status": False, "failReason": "private error",
            "serverAddressType": 1, "customAddress": "192.0.2.8",
            "radiusServerCertificate": {
                "cerId": "cert-id", "cerName": "private-cert", "keyId": "key-id",
                "keyName": "private-key", "keyPassword": "keystore-private",
                "cerType": "PFX",
            },
            "requireMessageAuthenticator": True, "limitProxyState": False,
        }
        projected = project_controller_radius_server(raw)
        self.assertEqual(projected["data"]["settings"], {
            "enabled": True, "tunnel_reply_enabled": False, "running": False,
            "require_message_authenticator": True, "limit_proxy_state": False,
            "auth_server_port": 1812, "server_address_type": 1,
        })
        self.assertEqual(projected["data"]["redacted_presence"], {
            "secret": True, "failure_reason": True, "custom_address": True,
            "certificate_configured": True,
        })
        for value in ("radius-private", "private error", "192.0.2.8", "cert-id",
                      "private-cert", "key-id", "private-key", "keystore-private"):
            self.assertNotIn(value, str(projected))
        self.assertFalse(projected["partial"])

    def test_empty_secrets_and_missing_or_invalid_fields_are_reported(self):
        projected = project_controller_radius_server({
            "enable": 1, "authServerPort": True, "secret": "",
            "tunnelReplyEnable": False, "serverAddressType": 0,
            "radiusServerCertificate": {"keyPassword": ""}, "extra": "hidden",
        })
        data = projected["data"]
        self.assertEqual(data["redacted_presence"], {
            "secret": False, "certificate_configured": False,
        })
        self.assertEqual(data["missing_required_count"], 0)
        self.assertEqual(data["invalid_count"], 2)
        self.assertEqual(data["unknown_field_count"], 1)
        self.assertTrue(projected["partial"])

    def test_rejects_non_objects_and_oversized_objects(self):
        for value in (None, [], {str(i): False for i in range(33)}):
            with self.subTest(value=type(value).__name__), self.assertRaisesRegex(
                    ControllerRadiusServerError, "response_invalid"):
                project_controller_radius_server(value)

    def test_conditional_response_requirements_mark_partial(self):
        projected = project_controller_radius_server({
            "enable": True, "authServerPort": 1812, "secret": "",
            "tunnelReplyEnable": True, "serverAddressType": 1, "status": False,
        })
        self.assertEqual(projected["data"]["missing_required_count"], 2)
        self.assertTrue(projected["partial"])


if __name__ == "__main__":
    unittest.main()
