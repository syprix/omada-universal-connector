import unittest
from unittest.mock import patch

from app.controller_certificate import project_controller_certificate
from app.controller_logging import project_controller_logging
from app.controller_status import project_controller_status
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerSystemReadProjectionTests(unittest.TestCase):
    def test_status_projects_capacity_versions_and_redacts_identifiers(self):
        result = project_controller_status({
            "name": "Private Controller", "macAddress": "02-00-00-00-00-01",
            "timeZone": "Europe/Berlin", "systemTime": 1000, "upTime": 600,
            "controllerVersion": "6.3.0", "category": "local",
            "model": "OC200", "firmwareVersion": "1.2.3",
            "hwcStorage": [{"name": "NVMe-Slot", "totalStorage": 10.0,
                            "usedStorage": 4.0, "ocStorage": True}],
            "deviceCapacity": {"adoptedApNum": 2, "apCapacity": 100,
                               "adoptedOswNum": 1, "oswCapacity": 50,
                               "adoptedOsgNum": 1, "osgCapacity": 20},
            "sn": "SERIAL-PRIVATE", "areaInfo": "private-area",
            "informUrl": "https://private.example/inform", "controllerType": 10,
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["status"]["uptime_seconds"], 600)
        self.assertEqual(result["data"]["status"]["capacity"]["ap_capacity"], 100)
        self.assertEqual(result["data"]["status"]["storage"]["used_storage"], 4.0)
        rendered = str(result)
        for secret in ("Private Controller", "02-00-00-00-00-01", "SERIAL-PRIVATE",
                       "private-area", "private.example", "Europe/Berlin", "NVMe-Slot"):
            self.assertNotIn(secret, rendered)
        self.assertEqual(result["data"]["presence"]["informUrl"], True)

    def test_status_marks_sparse_or_invalid_nested_data_partial(self):
        sparse = project_controller_status({
            "upTime": -1, "deviceCapacity": {"apCapacity": True},
            "hwcStorage": [{"totalStorage": 10 ** 1000}],
        })
        self.assertTrue(sparse["partial"])
        self.assertGreater(sparse["data"]["missing_count"], 0)
        self.assertEqual(sparse["data"]["invalid_count"], 3)

    def test_logging_accepts_only_documented_levels(self):
        result = project_controller_logging({
            "type": "CUSTOM", "otherModule": "WARN", "managerModule": "INFO",
            "clientModule": "DEBUG", "monitorModule": "WARN", "systemModule": "INFO",
            "accountModule": "DEBUG", "logModule": "WARN",
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["present_count"], 8)
        partial = project_controller_logging({"type": "AUTO", "clientModule": "TRACE"})
        self.assertTrue(partial["partial"])
        self.assertEqual(partial["data"]["invalid_count"], 1)

    def test_certificate_only_exposes_state_and_field_presence(self):
        result = project_controller_certificate({
            "cerId": "certificate-id", "cerName": "private-cert",
            "keyName": "private-key", "keyId": "key-id", "enable": True,
            "keyPassword": "key-secret", "trustPassword": "trust-secret",
            "cerType": "private-type",
        })
        self.assertFalse(result["partial"])
        self.assertTrue(result["data"]["enabled"])
        self.assertEqual(result["data"]["present_count"], 8)
        for secret in ("certificate-id", "private-cert", "private-key", "key-id",
                       "key-secret", "trust-secret", "private-type"):
            self.assertNotIn(secret, str(result))
        missing = project_controller_certificate({"enable": False})
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["data"]["required_missing_count"], 1)


class ControllerSystemReadIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_exact_fixed_controller_get_routes(self):
        cases = (
            (self.client.read_controller_status, "/openapi/v1/ctrl/system/setting/controller-status",
             {"controllerVersion": "6.3.0", "upTime": 12}),
            (self.client.read_controller_logging, "/openapi/v1/ctrl/system/setting/logging",
             {"type": "AUTO"}),
            (self.client.read_controller_certificate, "/openapi/v1/ctrl/system/setting/certificate",
             {"cerId": "secret", "enable": True}),
        )
        for method, path, raw in cases:
            with self.subTest(path=path), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
                response = method()
                request.assert_called_once_with("GET", path, token="token")
                self.assertEqual(response["status"], "ok")

    def test_unbound_controller_path_and_wrong_response_shape_fail_closed(self):
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", "/openapi/v1/other/system/setting/logging")
        for method in (self.client.read_controller_status, self.client.read_controller_logging,
                       self.client.read_controller_certificate):
            with patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": []}):
                with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                    method()


if __name__ == "__main__":
    unittest.main()
