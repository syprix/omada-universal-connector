import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerAdditionalReadsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def _assert_fixed_read(self, method, expected_path, resource, raw):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            response = getattr(self.client, method)()
        request.assert_called_once_with("GET", expected_path, token="token")
        self.assertEqual(response["resource"], resource)
        return response

    def test_backup_schedule_read_redacts_storage_details(self):
        result = self._assert_fixed_read(
            "read_controller_backup_schedule", "/openapi/v1/ctrl/backupschedule/task",
            "controller_backup_schedule", {
                "enable": True, "retention": 30, "savingPath": "/private/path",
                "fileServerConfig": {"password": "private-secret"},
            })
        self.assertTrue(result["data"]["enabled"])
        self.assertNotIn("private", repr(result))

    def test_cloud_access_read_redacts_owner(self):
        result = self._assert_fixed_read(
            "read_controller_cloud_access", "/openapi/v1/ctrl/cloud/status",
            "controller_cloud_access", {"enable": True, "status": 0, "owner": "private"})
        self.assertEqual(result["data"]["connection"], "disconnected")
        self.assertNotIn("private", repr(result))

    def test_device_management_read_uses_its_documented_global_path(self):
        result = self._assert_fixed_read(
            "read_controller_device_management", "/openapi/v1/ctrl/device-mgmt",
            "controller_device_management", {
                "webControlHttp": True, "webControlHttps": False, "appDiscovery": False,
            })
        self.assertTrue(result["data"]["settings"]["web_control_http"])

    def test_fixed_routes_reject_other_controller_ids(self):
        for path in ("/openapi/v1/other/backupschedule/task",
                     "/openapi/v1/other/cloud/status", "/openapi/v1/other/device-mgmt"):
            with self.subTest(path=path), self.assertRaisesRegex(
                    OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)


if __name__ == "__main__":
    unittest.main()
