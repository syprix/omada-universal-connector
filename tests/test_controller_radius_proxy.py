import unittest

from app.controller_radius_proxy import (
    ControllerRadiusProxyError,
    project_controller_radius_proxy,
)


class ControllerRadiusProxyTests(unittest.TestCase):
    def test_projects_documented_fields_and_redacts_failure_text(self):
        raw = {
            "enable": True, "port": 0, "status": False,
            "failReason": "private startup detail",
            "requireMessageAuthenticator": True, "limitProxyState": False,
        }
        result = project_controller_radius_proxy(raw)
        self.assertEqual(result["data"]["settings"], {
            "enabled": True, "running": False, "port": 0,
            "failure_reason_present": True,
            "require_message_authenticator": True,
            "limit_proxy_state": False,
        })
        self.assertNotIn("private startup detail", str(result))
        self.assertFalse(result["partial"])

    def test_invalid_unknown_and_missing_values_are_reported_without_raw_data(self):
        result = project_controller_radius_proxy({
            "enable": 1, "port": True, "status": "running",
            "failReason": {"private": "do-not-return"}, "newField": "secret",
        })
        self.assertEqual(result["data"]["invalid_count"], 4)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertEqual(result["data"]["missing_required_count"], 0)
        self.assertNotIn("do-not-return", str(result))
        self.assertTrue(result["partial"])

        missing = project_controller_radius_proxy({"enable": False})
        self.assertEqual(missing["data"]["missing_required_count"], 1)
        self.assertTrue(missing["partial"])

        failed_without_reason = project_controller_radius_proxy(
            {"enable": True, "port": 1812, "status": False})
        self.assertEqual(failed_without_reason["data"]["missing_required_count"], 1)

    def test_rejects_non_objects_and_oversized_objects(self):
        with self.assertRaisesRegex(ControllerRadiusProxyError, "response_invalid"):
            project_controller_radius_proxy(None)
        with self.assertRaisesRegex(ControllerRadiusProxyError, "response_invalid"):
            project_controller_radius_proxy({str(i): False for i in range(25)})


if __name__ == "__main__":
    unittest.main()
