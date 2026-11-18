import unittest
from unittest.mock import patch
import json

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerRadiusProxyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_read_route_and_failure_redaction(self):
        raw = {"enable": False, "port": 0, "status": False,
               "failReason": "private server startup detail"}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_controller_radius_proxy()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/global/controller/setting/network/radius-proxy",
            token="token")
        self.assertFalse(result["data"]["settings"]["enabled"])
        self.assertTrue(result["data"]["settings"]["failure_reason_present"])
        self.assertNotIn("private server startup detail", str(result))
        self.assertFalse(result["partial"])

    def test_upstream_error_is_propagated_without_payload(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json",
                             side_effect=OpenApiError("controller_error")):
            with self.assertRaisesRegex(OpenApiError, "controller_error"):
                self.client.read_controller_radius_proxy()

    def test_fixed_route_rejects_a_different_controller_id(self):
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/other/global/controller/setting/network/radius-proxy")

    def test_patch_requires_write_guard_and_sends_only_documented_fields(self):
        with self.assertRaisesRegex(OpenApiError, "operator_approval_required"):
            self.client._request_json(
                "PATCH", "/openapi/v1/ctrl/global/controller/setting/network/radius-proxy",
                body=b'{"enable":true,"port":1812}')

        class Response:
            status = 200

            def getheader(self, _name, default=""):
                return "application/json"

            def read(self, _limit):
                return b'{"errorCode":0,"msg":"safe acknowledgement"}'

        class Connection:
            _omada_tls_verified = False

            def __init__(self):
                self.args = None

            def request(self, method, path, body=None, headers=None):
                self.args = (method, path, body, headers)

            def getresponse(self):
                return Response()

            def close(self):
                pass

        connection = Connection()
        self.client._write_dispatch_guard = lambda: None
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_connection", return_value=connection):
            self.client.patch_controller_radius_proxy({"enable": True, "port": 1812})
        self.assertEqual(connection.args[0:2], (
            "PATCH", "/openapi/v1/ctrl/global/controller/setting/network/radius-proxy"))
        self.assertEqual(json.loads(connection.args[2]), {"enable": True, "port": 1812})

    def test_patch_rejects_unknown_fields_and_boolean_port(self):
        for state in ({"enable": True, "port": 1812, "secret": "never"},
                      {"enable": True, "port": True}):
            with self.subTest(state=state):
                with self.assertRaisesRegex(OpenApiError, "controller_radius_proxy_change_invalid"):
                    self.client.patch_controller_radius_proxy(state)


if __name__ == "__main__":
    unittest.main()
