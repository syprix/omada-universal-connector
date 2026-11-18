import unittest

from app.controller_device_access import (
    ControllerDeviceAccessError,
    project_controller_device_access,
)


class ControllerDeviceAccessTests(unittest.TestCase):
    def test_projects_documented_boolean_switches(self):
        result = project_controller_device_access({
            "webControlHttp": False,
            "webControlHttps": True,
            "appDiscovery": True,
        })
        self.assertEqual(result["data"]["settings"], {
            "web_control_http": False,
            "web_control_https": True,
            "app_discovery": True,
        })
        self.assertFalse(result["partial"])

    def test_missing_invalid_and_unknown_fields_are_explicit(self):
        result = project_controller_device_access({
            "webControlHttp": 1,
            "webControlHttps": True,
            "privateValue": "do-not-return",
        })
        self.assertEqual(result["data"]["settings"], {"web_control_https": True})
        self.assertEqual(result["data"]["missing_count"], 1)
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("do-not-return", str(result))
        self.assertTrue(result["partial"])

    def test_rejects_non_object_and_oversized_responses(self):
        with self.assertRaisesRegex(ControllerDeviceAccessError, "response_invalid"):
            project_controller_device_access([])
        with self.assertRaisesRegex(ControllerDeviceAccessError, "response_invalid"):
            project_controller_device_access({str(i): False for i in range(17)})


if __name__ == "__main__":
    unittest.main()
