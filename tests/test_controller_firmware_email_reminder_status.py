import unittest
from unittest.mock import patch

from app.controller_firmware_email_reminder_status import (
    ControllerFirmwareEmailReminderStatusError,
    project_firmware_email_reminder_status,
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


class ControllerFirmwareEmailReminderStatusTests(unittest.TestCase):
    def client(self):
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64,
        ))

    def test_strict_true_false_and_incomplete_shapes(self):
        for value in (True, False):
            with self.subTest(value=value):
                result = project_firmware_email_reminder_status({"enable": value})
                self.assertIs(result["data"]["firmware_email_reminder_enabled"], value)
                self.assertFalse(result["partial"])
        for result_data in ({}, {"enable": None}, {"enable": 0}, {"enable": "false"}):
            with self.subTest(result_data=result_data):
                result = project_firmware_email_reminder_status(result_data)
                self.assertIsNone(result["data"]["firmware_email_reminder_enabled"])
                self.assertTrue(result["partial"])

    def test_unknown_and_non_object_data_are_safely_handled(self):
        result = project_firmware_email_reminder_status({
            "enable": True, "recipient": "private@example.invalid",
            "secret": "private-value",
        })
        self.assertEqual(result["data"]["unknown_field_count"], 2)
        self.assertTrue(result["data"]["firmware_email_reminder_enabled"])
        self.assertNotIn("private", repr(result))
        self.assertTrue(result["partial"])
        for value in (None, [], "invalid", {str(i): i for i in range(9)}):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(ControllerFirmwareEmailReminderStatusError):
                    project_firmware_email_reminder_status(value)

    def test_connector_uses_only_fixed_controller_get_and_preserves_errors(self):
        client = self.client()
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={
                    "result": {"enable": False}}) as request:
            result = client.read_controller_firmware_email_reminder_status()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/upgrade/overview/mail/reminder", token="test-token")
        self.assertFalse(result["data"]["firmware_email_reminder_enabled"])
        self.assertEqual(result["resource"], "controller_firmware_email_reminder_status")
        self.assertTrue(client._controller_firmware_email_reminder_status_request_valid(
            "/openapi/v1/ctrl/upgrade/overview/mail/reminder"))
        for path in (
            "/openapi/v1/other/upgrade/overview/mail/reminder",
            "/openapi/v1/ctrl/upgrade/overview/mail/reminder?x=1",
            "/openapi/v2/ctrl/upgrade/overview/mail/reminder",
        ):
            self.assertFalse(client._controller_firmware_email_reminder_status_request_valid(path))
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", side_effect=OpenApiError(
                    "openapi_rejected", upstream_error_code=-1501,
                    upstream_http_status=403)):
            with self.assertRaises(OpenApiError) as caught:
                client.read_controller_firmware_email_reminder_status()
        self.assertEqual(caught.exception.code, "openapi_rejected")
        self.assertEqual(caught.exception.upstream_error_code, -1501)
        self.assertEqual(caught.exception.upstream_http_status, 403)

    def test_fixed_route_passes_allowlist_and_mismatch_fails_before_connection(self):
        client = self.client()
        connection = FakeConnection({"errorCode": 0, "result": {"enable": True}})
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_connection", return_value=connection):
            result = client.read_controller_firmware_email_reminder_status()
        self.assertTrue(result["data"]["firmware_email_reminder_enabled"])
        self.assertEqual(connection.request_args[:3], (
            "GET", "/openapi/v1/ctrl/upgrade/overview/mail/reminder", None))
        wrong = FakeConnection({"errorCode": 0, "result": {"enable": True}})
        with patch.object(client, "_connection", return_value=wrong) as connection_factory:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET", "/openapi/v1/other/upgrade/overview/mail/reminder")
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("POST", "/openapi/v1/ctrl/upgrade/overview/mail/reminder")
        connection_factory.assert_not_called()

    def test_registry_http_shape_and_mcp_read_only_dispatch(self):
        operation = REGISTRY.get("controller_firmware_email_reminder_status")
        self.assertEqual(operation.public_template,
                         "/v1/controller/firmware-email-reminder/status")
        self.assertEqual(operation.upstream_template,
                         "/openapi/v1/{controller_id}/upgrade/overview/mail/reminder")
        route, bindings = REGISTRY.match(
            "GET", "/v1/controller/firmware-email-reminder/status")
        self.assertEqual(route.operation_id, operation.operation_id)
        self.assertEqual(dict(bindings), {})
        with self.assertRaises(RegistryError):
            REGISTRY.match("POST", "/v1/controller/firmware-email-reminder/status")
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        page = handle_mcp_request(request, None, REGISTRY, lambda *_: {})["result"]
        tools = list(page["tools"])
        while "nextCursor" in page:
            page = handle_mcp_request({**request, "params": {
                "cursor": page["nextCursor"]}}, None, REGISTRY, lambda *_: {})["result"]
            tools.extend(page["tools"])
        tool = next(t for t in tools
                    if t["name"] == "omada_controller_firmware_email_reminder_status")
        self.assertEqual(tool["inputSchema"]["required"], [])
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertFalse(tool["annotations"]["destructiveHint"])
        calls = []
        def invoke(operation_id, arguments):
            calls.append((operation_id, arguments))
            return {"status": "ok", "resource": operation_id,
                    "data": {"firmware_email_reminder_enabled": False}, "partial": False}
        response = handle_mcp_request({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "omada_controller_firmware_email_reminder_status",
                       "arguments": {}}}, None, REGISTRY, invoke)
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(calls, [("controller_firmware_email_reminder_status", {})])
        bad = handle_mcp_request({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "omada_controller_firmware_email_reminder_status",
                       "arguments": {"path": "/arbitrary"}}}, None, REGISTRY, invoke)
        self.assertEqual(bad["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
