from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.openapi import OpenApiError
from tools import setup_check


class _Connection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Controller:
    def __init__(self, *, tls_error: str | None = None,
                 auth_error: str | None = None, read_error: str | None = None) -> None:
        self.tls_error, self.auth_error, self.read_error = tls_error, auth_error, read_error
        self.config = SimpleNamespace(client_id_file="/private/client-id",
                                      client_secret_file="/private/client-secret",
                                      controller_id="controller-id")
        self.connection = _Connection()
        self.calls: list[str] = []

    def _connection(self):
        self.calls.append("tls")
        if self.tls_error:
            raise OpenApiError(self.tls_error)
        return self.connection

    def _access_token(self):
        self.calls.append("authentication")
        if self.auth_error:
            raise OpenApiError(self.auth_error)
        return "unobserved-test-token"

    def _read_pages(self, path: str, token: str):
        self.calls.append("read_permission")
        if path != "/openapi/v1/controller-id/sites" or token != "unobserved-test-token":
            raise OpenApiError("openapi_path_rejected")
        if self.read_error:
            raise OpenApiError(self.read_error)
        return [{"site_ref": "a" * 24}, {"site_ref": "b" * 24}]


class _McpResponse:
    status = 200

    def __init__(self, payload: object, *, status: int = 200) -> None:
        self.status = status
        self.body = json.dumps(payload).encode()

    def getheader(self, _name: str, default: str = "") -> str:
        return "application/json" if _name.lower() == "content-type" else default

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


class _McpConnection:
    def __init__(self, responses: _McpResponse | list[_McpResponse]) -> None:
        self.responses = responses if isinstance(responses, list) else [responses]
        self.requests: list[tuple[str, str, bytes, dict[str, str]]] = []
        self.closed = False

    def request(self, method: str, path: str, body: bytes,
                headers: dict[str, str]) -> None:
        self.requests.append((method, path, body, headers))

    def getresponse(self) -> _McpResponse:
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


class SetupCheckTests(unittest.TestCase):
    def test_controller_steps_are_separate_and_inventory_is_count_only(self) -> None:
        client = _Controller()
        checks = setup_check._controller_checks(client, None)
        self.assertEqual([item["name"] for item in checks],
                         ["tls", "authentication", "read_permission"])
        self.assertEqual([item["status"] for item in checks], ["ok", "ok", "ok"])
        self.assertEqual(checks[-1]["site_count"], 2)
        self.assertEqual(client.calls, ["tls", "authentication", "read_permission"])
        self.assertTrue(client.connection.closed)
        self.assertNotIn("token", repr(checks).lower())

    def test_tls_failure_skips_authentication_and_permissions(self) -> None:
        client = _Controller(tls_error="controller_certificate_changed")
        checks = setup_check._controller_checks(client, None)
        self.assertEqual([item["status"] for item in checks], ["error", "not_run", "not_run"])
        self.assertEqual(checks[0]["code"], "controller_certificate_changed")
        self.assertEqual(client.calls, ["tls"])

    def test_authentication_and_permission_failures_are_distinguished(self) -> None:
        auth = _Controller(auth_error="openapi_authentication_failed")
        checks = setup_check._controller_checks(auth, None)
        self.assertEqual([item["status"] for item in checks], ["ok", "error", "not_run"])
        self.assertEqual(checks[1]["code"], "openapi_authentication_failed")
        self.assertEqual(auth.calls, ["tls", "authentication"])

        permission = _Controller(read_error="openapi_permission_denied")
        checks = setup_check._controller_checks(permission, None)
        self.assertEqual([item["status"] for item in checks], ["ok", "ok", "error"])
        self.assertIn("Standortinventar", checks[-1]["detail"])

    def test_missing_client_credential_paths_do_not_hide_tls_failure(self) -> None:
        client = _Controller()
        client.config.client_secret_file = ""
        checks = setup_check._controller_checks(client, None)
        self.assertEqual([item["status"] for item in checks], ["ok", "error", "not_run"])
        self.assertEqual(checks[1]["code"], "credential_file_not_configured")
        self.assertEqual(client.calls, ["tls"])

    def test_connector_addresses_do_not_send_cleartext_tokens_remotely(self) -> None:
        self.assertEqual(setup_check._connector_address("http://localhost:8080"),
                         ("http", "localhost", 8080))
        self.assertEqual(setup_check._connector_address("https://connector.example"),
                         ("https", "connector.example", 443))
        with self.assertRaisesRegex(ValueError, "connector_url_invalid"):
            setup_check._connector_address("http://connector.example:8080")

    def test_mcp_initialize_handshake_uses_token_and_returns_no_secret(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory) / "connector-token"
            token_path.write_text("c" * 48, encoding="ascii")
            token_path.chmod(0o600)
            connection = _McpConnection([
                _McpResponse({
                    "jsonrpc": "2.0", "id": "setup-check-initialize",
                    "result": {"protocolVersion": "2025-06-18",
                               "serverInfo": {"name": "omada-universal-connector",
                                              "version": "0.3.0"}},
                }),
                _McpResponse({"jsonrpc": "2.0", "id": "setup-check-tools-0",
                              "result": {"tools": [{"name": "omada_health"}],
                                         "nextCursor": "25"}}),
                _McpResponse({"jsonrpc": "2.0", "id": "setup-check-tools-1",
                              "result": {"tools": [{"name": "omada_sites",
                                                     "annotations": {"readOnlyHint": True}}]}}),
                _McpResponse({"jsonrpc": "2.0", "id": "setup-check-read",
                              "result": {"isError": False, "structuredContent": {
                                  "status": "ok", "resource": "sites", "items": []}}}),
                _McpResponse({"jsonrpc": "2.0", "id": "setup-check-error",
                              "error": {"code": -32601, "message": "tool_unknown"}}),
            ])
            with patch.object(setup_check.http.client, "HTTPConnection", return_value=connection):
                result = setup_check._mcp_check("http://127.0.0.1:8080", str(token_path))
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["protocol_version"], "2025-06-18")
            self.assertEqual(result["tool_count"], 2)
            self.assertEqual(result["safe_read_tool"], "omada_sites")
            self.assertEqual(result["error_path"], "tool_unknown")
            self.assertEqual(len(connection.requests), 5)
            self.assertEqual(json.loads(connection.requests[2][2])["params"], {"cursor": "25"})
            method, path, _body, headers = connection.requests[0]
            self.assertEqual((method, path), ("POST", "/mcp"))
            self.assertEqual(headers["Authorization"], "Bearer " + "c" * 48)
            self.assertNotIn("c" * 48, repr(result))
            self.assertTrue(connection.closed)

    def test_mcp_smoke_checks_safe_read_and_expected_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory) / "connector-token"
            token_path.write_text("c" * 48, encoding="ascii")
            token_path.chmod(0o600)
            initialized = _McpResponse({
                "jsonrpc": "2.0", "id": "setup-check-initialize",
                "result": {"protocolVersion": "2025-06-18",
                           "serverInfo": {"name": "omada-universal-connector",
                                          "version": "0.3.0"}},
            })
            listed = _McpResponse({"jsonrpc": "2.0", "id": "setup-check-tools-0",
                                    "result": {"tools": [{"name": "omada_sites",
                                                           "annotations": {"readOnlyHint": True}}]}})
            for safe_read_result, error_result, expected in (
                ({"isError": True, "structuredContent": {"status": "error"}},
                 {"code": -32601, "message": "tool_unknown"}, "mcp_safe_read_failed"),
                ({"isError": False, "structuredContent": {"status": "ok", "resource": "sites",
                                                             "items": []}},
                 {"code": -32602, "message": "arguments_invalid"}, "mcp_error_handling_failed"),
            ):
                connection = _McpConnection([
                    initialized, listed,
                    _McpResponse({"jsonrpc": "2.0", "id": "setup-check-read",
                                  "result": safe_read_result}),
                    _McpResponse({"jsonrpc": "2.0", "id": "setup-check-error",
                                  "error": error_result}),
                ])
                with patch.object(setup_check.http.client, "HTTPConnection", return_value=connection):
                    result = setup_check._mcp_check("http://127.0.0.1:8080", str(token_path))
                self.assertEqual(result["code"], expected)

    def test_mcp_safe_read_must_be_advertised_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory) / "connector-token"
            token_path.write_text("c" * 48, encoding="ascii")
            token_path.chmod(0o600)
            connection = _McpConnection([
                _McpResponse({"jsonrpc": "2.0", "id": "setup-check-initialize",
                              "result": {"protocolVersion": "2025-06-18",
                                         "serverInfo": {"name": "omada-universal-connector",
                                                        "version": "0.3.0"}}}),
                _McpResponse({"jsonrpc": "2.0", "id": "setup-check-tools-0",
                              "result": {"tools": [{"name": "omada_sites",
                                                     "annotations": {"readOnlyHint": False}}]}}),
            ])
            with patch.object(setup_check.http.client, "HTTPConnection", return_value=connection):
                result = setup_check._mcp_check("http://127.0.0.1:8080", str(token_path))
            self.assertEqual(result["code"], "mcp_tools_list_invalid")
            self.assertEqual(len(connection.requests), 2)

    def test_bad_mcp_response_and_bad_token_file_have_specific_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory) / "connector-token"
            token_path.write_text("c" * 48, encoding="ascii")
            token_path.chmod(0o600)
            connection = _McpConnection(_McpResponse({"jsonrpc": "2.0", "id": "wrong"}))
            with patch.object(setup_check.http.client, "HTTPConnection", return_value=connection):
                result = setup_check._mcp_check("http://127.0.0.1:8080", str(token_path))
            self.assertEqual(result["code"], "mcp_handshake_invalid")
            token_path.chmod(0o644)
            result = setup_check._mcp_check("http://127.0.0.1:8080", str(token_path))
            self.assertEqual(result["code"], "connector_token_invalid")

    def test_setup_result_marks_unconfigured_independent_mcp_step(self) -> None:
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(setup_check, "_mcp_check", return_value={
                    "name": "mcp", "status": "error",
                    "code": "connector_token_not_configured",
                }) as mcp:
            result = setup_check.run_setup_check(config_error="openapi_configuration_missing")
        mcp.assert_called_once_with("http://127.0.0.1:18080", None)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual([item["name"] for item in result["checks"]],
                         ["configuration", "tls", "authentication", "read_permission", "mcp"])
        self.assertEqual(result["checks"][-1]["code"], "connector_token_not_configured")
        self.assertTrue(result["read_only"])


if __name__ == "__main__":
    unittest.main()
