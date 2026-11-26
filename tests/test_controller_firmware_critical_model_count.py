import unittest
from unittest.mock import patch

from app.controller_firmware_critical_model_count import (
    ControllerFirmwareCriticalModelCountError,
    project_critical_model_count,
)
from app.mcp import handle_mcp_request
from app.operation_registry import REGISTRY, RegistryError
from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient


class FakeResponse:
    status = 200

    def __init__(self, payload):
        import json
        self.raw = json.dumps(payload).encode()

    def read(self, limit=-1):
        return self.raw[:limit]

    def getheader(self, name, default=""):
        return "application/json" if name.lower() == "content-type" else default


class FakeConnection:
    _omada_tls_verified = True

    def __init__(self, payload):
        self.response = FakeResponse(payload)
        self.request_args = None

    def request(self, method, path, body=None, headers=None):
        self.request_args = (method, path, body, headers)

    def getresponse(self):
        return self.response

    def close(self):
        pass


class ControllerFirmwareCriticalModelCountTests(unittest.TestCase):
    def client(self):
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64,
        ))

    def test_nonnegative_int32_and_explicit_zero_are_complete(self):
        for value in (0, 4, (1 << 31) - 1):
            with self.subTest(value=value):
                result = project_critical_model_count({"criticalNumber": value})
                self.assertEqual(result["critical_model_count"], value)
                self.assertTrue(result["count_present"])
                self.assertTrue(result["coverage_complete"])
                self.assertFalse(result["partial"])

    def test_missing_invalid_and_unknown_fields_remain_incomplete(self):
        missing = project_critical_model_count({})
        self.assertIsNone(missing["critical_model_count"])
        self.assertEqual(missing["missing_field_count"], 1)
        self.assertTrue(missing["partial"])

        for value in (True, -1, 1 << 31, "3", 3.0):
            with self.subTest(value=value):
                result = project_critical_model_count({"criticalNumber": value})
                self.assertIsNone(result["critical_model_count"])
                self.assertEqual(result["invalid_field_count"], 1)
                self.assertTrue(result["partial"])

        result = project_critical_model_count({"criticalNumber": 2, "unrecognized": "private"})
        self.assertEqual(result["critical_model_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("unrecognized", repr(result))
        self.assertNotIn("private", repr(result))

    def test_non_object_response_is_sanitized(self):
        with self.assertRaises(ControllerFirmwareCriticalModelCountError):
            project_critical_model_count([{"criticalNumber": 1}])

    def test_connector_uses_only_the_fixed_controller_route(self):
        client = self.client()
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "criticalNumber": 0}}) as request:
            result = client.read_controller_firmware_critical_model_count()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/upgrade/overview/critical", token="test-token")
        self.assertEqual(result["critical_model_count"], 0)
        self.assertEqual(result["resource"], "controller_firmware_critical_model_count")
        self.assertTrue(client._controller_firmware_critical_model_count_request_valid(
            "/openapi/v1/ctrl/upgrade/overview/critical"))
        for path in (
            "/openapi/v1/other/upgrade/overview/critical",
            "/openapi/v1/ctrl/upgrade/overview/critical?extra=1",
            "/openapi/v2/ctrl/upgrade/overview/critical",
        ):
            with self.subTest(path=path):
                self.assertFalse(client._controller_firmware_critical_model_count_request_valid(path))

    def test_controller_error_code_remains_on_standard_connector_error(self):
        client = self.client()
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", side_effect=OpenApiError(
                    "openapi_rejected", upstream_error_code=-1501,
                    upstream_http_status=403)):
            with self.assertRaises(OpenApiError) as caught:
                client.read_controller_firmware_critical_model_count()
        self.assertEqual(caught.exception.code, "openapi_rejected")
        self.assertEqual(caught.exception.upstream_error_code, -1501)
        self.assertEqual(caught.exception.upstream_http_status, 403)

    def test_fixed_route_passes_allowlist_and_numeric_upstream_error_is_preserved(self):
        client = self.client()
        connection = FakeConnection({"errorCode": 0, "result": {"criticalNumber": 7}})
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_connection", return_value=connection):
            result = client.read_controller_firmware_critical_model_count()
        self.assertEqual(result["critical_model_count"], 7)
        self.assertEqual(connection.request_args[:3], (
            "GET", "/openapi/v1/ctrl/upgrade/overview/critical", None))
        self.assertEqual(connection.request_args[3]["Authorization"], "AccessToken=test-token")

        denied = FakeConnection({"errorCode": -1501})
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_connection", return_value=denied):
            with self.assertRaises(OpenApiError) as caught:
                client.read_controller_firmware_critical_model_count()
        self.assertEqual(caught.exception.code, "openapi_rejected")
        self.assertEqual(caught.exception.upstream_error_code, -1501)
        self.assertEqual(caught.exception.upstream_http_status, 200)
        capability = next(item for item in client.capabilities()["items"]
                          if item["operation"] == "controller_firmware_critical_model_count")
        self.assertEqual(capability["runtime_evidence"][0]["upstream_error_code"], -1501)

        wrong = FakeConnection({"errorCode": 0, "result": {"criticalNumber": 1}})
        with patch.object(client, "_connection", return_value=wrong) as connection_factory:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET", "/openapi/v1/other/upgrade/overview/critical")
        connection_factory.assert_not_called()

    def test_operation_is_fixed_read_only_and_exposed_through_mcp(self):
        operation = REGISTRY.get("controller_firmware_critical_model_count")
        self.assertEqual(operation.public_template,
                         "/v1/controller/firmware-critical-model-count/summary")
        self.assertEqual(operation.upstream_template,
                         "/openapi/v1/{controller_id}/upgrade/overview/critical")
        route, bindings = REGISTRY.match(
            "GET", "/v1/controller/firmware-critical-model-count/summary")
        self.assertEqual(route.operation_id, operation.operation_id)
        self.assertEqual(dict(bindings), {})
        client = self.client()
        capability_route = dict(client.CAPABILITY_OPERATIONS)[operation.operation_id]
        self.assertEqual(capability_route,
                         "GET /v1/controller/firmware-critical-model-count/summary")
        with self.assertRaises(RegistryError):
            REGISTRY.match("POST", "/v1/controller/firmware-critical-model-count/summary")

        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        page = handle_mcp_request(request, None, REGISTRY, lambda *_: {})["result"]
        tools = list(page["tools"])
        while "nextCursor" in page:
            page = handle_mcp_request({**request, "params": {
                "cursor": page["nextCursor"]}}, None, REGISTRY, lambda *_: {})["result"]
            tools.extend(page["tools"])
        tool = next(t for t in tools
                    if t["name"] == "omada_controller_firmware_critical_model_count")
        self.assertEqual(tool["inputSchema"]["required"], [])
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertFalse(tool["annotations"]["destructiveHint"])

        calls = []
        def invoke(operation_id, arguments):
            calls.append((operation_id, arguments))
            return {"status": "ok", "resource": operation_id,
                    "critical_model_count": 0, "coverage_complete": True,
                    "partial": False}

        result = handle_mcp_request({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "omada_controller_firmware_critical_model_count",
                       "arguments": {}}}, None, REGISTRY, invoke)
        self.assertFalse(result["result"]["isError"])
        self.assertEqual(calls, [("controller_firmware_critical_model_count", {})])
        rejected = handle_mcp_request({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "omada_controller_firmware_critical_model_count",
                       "arguments": {"path": "/arbitrary"}}}, None, REGISTRY, invoke)
        self.assertIn("error", rejected)
        self.assertEqual(rejected["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
