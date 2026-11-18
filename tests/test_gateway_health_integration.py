from __future__ import annotations

import builtins
import io
import json
import os
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF = "a" * 24
GATEWAY_REF = "b" * 24
GATEWAY_MAC = "AA-BB-CC-DD-EE-FF"
PRIVATE_SITE_ID = "site_private"
PRIVATE_INCIDENT = "raw incident id"
PRIVATE_TEXT = "private controller message"


class GatewayHealthIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.token = "fixture-caller-token-0123456789abcdef"
        self.token_file = os.path.join(self.tempdir.name, "caller-token")
        with open(self.token_file, "w", encoding="utf-8") as handle:
            handle.write(self.token)
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id-file", "secret-file",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = PRIVATE_SITE_ID
        self.client._gateway_macs_by_site_ref[SITE_REF] = {GATEWAY_REF: GATEWAY_MAC}
        self.upstream: list[tuple[str, str, bytes | None]] = []
        self.result: object = {
            "score": 90,
            "cpu": {"summaryScore": 88, "averageNum": 17,
                    "pastNums": [{"time": 0, "pastNum": 12}],
                    "name": "private cpu label"},
            "incident": {"incidentNum": 1,
                         "incidents": [{"id": PRIVATE_INCIDENT,
                                        "description": PRIVATE_TEXT}]},
            "internalId": PRIVATE_INCIDENT,
        }

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.upstream.append((method, path, body))
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(token, "fixture-upstream-token")
            expected_prefix = ("/openapi/v1/ctrl/sites/site_private/gateways/"
                               "AA-BB-CC-DD-EE-FF/health/detail?")
            self.assertTrue(path.startswith(expected_prefix))
            query = parse_qs(urlsplit(path).query)
            start, end = int(query["start"][0]), int(query["end"][0])
            self.assertEqual(set(query), {"start", "end"})
            self.assertEqual(end - start, 86_400_000)
            if isinstance(self.result, dict):
                cpu = self.result.get("cpu")
                if isinstance(cpu, dict) and isinstance(cpu.get("pastNums"), list):
                    cpu["pastNums"][0]["time"] = end
            return {"result": self.result}

        self.request_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.request_patch.start()
        self.access_patch = patch.object(self.client, "_access_token",
                                          return_value="fixture-upstream-token")
        self.access_patch.start()
        self.env_patch = patch.dict(os.environ, {
            "OMADA_CONNECTOR_TOKEN_FILE": self.token_file,
        })
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.logs = io.StringIO()
        self.log_patch = patch.object(builtins, "print",
                                      lambda *args, **_kwargs: self.logs.write(
                                          " ".join(map(str, args)) + "\n"))
        self.log_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.log_patch.stop()
        self.client_patch.stop()
        self.env_patch.stop()
        self.access_patch.stop()
        self.request_patch.stop()
        self.tempdir.cleanup()

    @staticmethod
    def _path(site_ref: str = SITE_REF, gateway_ref: str = GATEWAY_REF) -> str:
        return f"/v1/sites/{site_ref}/gateways/{gateway_ref}/health"

    def request(self, method: str, path: str, *, token: str | None = None,
                body: dict[str, object] | None = None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {}
        connection.close()
        return response.status, result

    def test_mcp_tool_dispatches_the_fixed_health_route(self) -> None:
        status, response = self.request(
            "POST", "/mcp", token=self.token,
            body={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": "omada_gateway_health",
                             "arguments": {"site_ref": SITE_REF,
                                           "gateway_ref": GATEWAY_REF}}})
        self.assertEqual(status, 200)
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "gateway_health")
        self.assertEqual(len(self.upstream), 1)

    def test_authenticated_fixed_millisecond_window_redaction_and_capability(self) -> None:
        status, error = self.request("GET", self._path())
        self.assertEqual(status, 401)
        self.assertEqual(error["error"], "unauthorized")
        self.assertEqual(self.upstream, [])

        status, result = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 200)
        method, path, body = self.upstream[0]
        self.assertEqual(method, "GET")
        self.assertIsNone(body)
        query = parse_qs(urlsplit(path).query)
        start, end = int(query["start"][0]), int(query["end"][0])
        self.assertEqual(end - start, 86_400_000)
        self.assertLess(abs(end - int(time.time() * 1000)), 5_000)
        self.assertGreater(end, 100_000_000_000)  # milliseconds, not seconds
        self.assertEqual(result["window_start_ms"], start)
        self.assertEqual(result["window_end_ms"], end)
        self.assertEqual(result["gateway_ref"], GATEWAY_REF)
        rendered = json.dumps(result)
        for private in (PRIVATE_SITE_ID, GATEWAY_MAC, PRIVATE_INCIDENT, PRIVATE_TEXT,
                        "private cpu label", "internalId"):
            self.assertNotIn(private, rendered)
        for private in (SITE_REF, GATEWAY_REF, PRIVATE_SITE_ID, GATEWAY_MAC,
                        PRIVATE_INCIDENT, PRIVATE_TEXT):
            self.assertNotIn(private, self.logs.getvalue())

        status, catalog = self.request("GET", "/v1/capabilities", token=self.token)
        self.assertEqual(status, 200)
        capability = next(item for item in catalog["items"]
                          if item["operation"] == "gateway_health")
        evidence = capability["runtime_evidence"][0]
        self.assertEqual(evidence["result"], "success")
        self.assertEqual(evidence["target_ref"], SITE_REF + ":" + GATEWAY_REF)

    def test_unknown_inventory_refs_are_rejected_before_upstream_read(self) -> None:
        for path, expected in ((self._path("c" * 24), "site_ref_unknown"),
                               (self._path(gateway_ref="d" * 24), "gateway_ref_unknown")):
            before = len(self.upstream)
            status, error = self.request("GET", path, token=self.token)
            self.assertEqual(status, 502)
            self.assertEqual(error["error"], expected)
            self.assertEqual(len(self.upstream), before)

    def test_invalid_projector_response_is_redacted_error(self) -> None:
        self.result = {"cpu": "not-a-dimension", "raw": PRIVATE_TEXT}
        status, error = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_response_invalid")
        self.assertNotIn(PRIVATE_TEXT, str(error))

    def test_route_is_get_only_and_malformed_paths_do_not_dispatch(self) -> None:
        status, _ = self.request("POST", self._path(), token=self.token)
        self.assertEqual(status, 501)
        status, error = self.request("GET", self._path(gateway_ref="not-a-ref"),
                                     token=self.token)
        self.assertEqual(status, 404)
        self.assertEqual(error["error"], "not_found")
        self.assertEqual(self.upstream, [])

    def test_upstream_allowlist_pins_controller_method_shape_and_millisecond_window(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id-file", "secret-file",
            cert_sha256="a" * 64))
        good = ("/openapi/v1/ctrl/sites/site_1/gateways/00:11:22:33:44:55/health/detail"
                "?start=1000000000000&end=1000086400000")
        with patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", good, token="token")
            for method, path in (
                ("GET", good.replace("/ctrl/", "/foreign/")),
                ("GET", good.replace("end=1000086400000", "end=1000086399999")),
                ("GET", good.replace("1000000000000", "1000000000")
                 .replace("1000086400000", "1000086400")),
                ("GET", good + "&extra=1"),
                ("POST", good),
            ):
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, token="token")


if __name__ == "__main__":
    unittest.main()
