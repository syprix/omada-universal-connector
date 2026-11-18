from __future__ import annotations

import builtins
import io
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


TOKEN = "gateway-health-timeline-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
GATEWAY_REF = "c" * 24
OTHER_GATEWAY_REF = "d" * 24
PRIVATE_SITE_ID = "private-site-id"
GATEWAY_MAC = "AA-BB-CC-DD-EE-FF"
OTHER_GATEWAY_MAC = "11:22:33:44:55:66"
PRIVATE_MARKERS = (
    "private-gateway-name", "192.0.2.30", "private-network-id",
    "private-score-id", "private-controller-text",
)
DAY_MS = 86_400_000


class FixedDateTime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 2, 3, 12, 0, tzinfo=tz or timezone.utc)


class GatewayHealthTimelineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(TOKEN)
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = PRIVATE_SITE_ID
        self.client._gateway_macs_by_site_ref[SITE_REF] = {GATEWAY_REF: GATEWAY_MAC}
        self.client._gateway_macs_by_site_ref[OTHER_SITE_REF] = {
            OTHER_GATEWAY_REF: OTHER_GATEWAY_MAC,
        }
        end_ms = int(FixedDateTime.now(timezone.utc).timestamp() * 1000)
        self.start_ms, self.end_ms = end_ms - DAY_MS, end_ms
        self.result: object = {"scores": [
            {"time": self.start_ms, "score": 83},
            {"time": self.end_ms, "score": 91},
        ]}
        self.upstream_calls: list[tuple[str, str, bytes | None]] = []
        self.fail_upstream = False

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.upstream_calls.append((method, path, body))
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(token, "synthetic-upstream-token")
            parsed = urlsplit(path)
            self.assertEqual(parsed.path,
                f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/gateways/{GATEWAY_MAC}/health/timeline")
            query = parse_qs(parsed.query, strict_parsing=True)
            self.assertEqual(set(query), {"start", "end"})
            start, end = int(query["start"][0]), int(query["end"][0])
            self.assertEqual(end - start, DAY_MS)
            self.assertEqual((start, end), (self.start_ms, self.end_ms))
            if self.fail_upstream:
                raise OpenApiError("openapi_rejected", -1001)
            return {"result": json.loads(json.dumps(self.result))}

        self.transport_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.transport_patch.start()
        self.access_patch = patch.object(
            self.client, "_access_token", return_value="synthetic-upstream-token")
        self.access_patch.start()
        self.clock_patch = patch("app.openapi.datetime", FixedDateTime)
        self.clock_patch.start()
        self.env_patch = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": self.token_file})
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.logs = io.StringIO()
        self.print_patch = patch.object(
            builtins, "print", lambda *args, **_kwargs: self.logs.write(
                " ".join(map(str, args)) + "\n"))
        self.print_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.print_patch.stop()
        self.client_patch.stop()
        self.env_patch.stop()
        self.clock_patch.stop()
        self.access_patch.stop()
        self.transport_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def public_path(site_ref: str = SITE_REF, gateway_ref: str = GATEWAY_REF) -> str:
        return f"/v1/sites/{site_ref}/gateways/{gateway_ref}/health/timeline"

    def request(self, method: str, path: str, *, token: str | None = None,
                body: dict[str, object] | None = None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + token} if token is not None else {}
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = {}
        status = response.status
        connection.close()
        return status, value

    def test_mcp_tool_dispatches_the_fixed_health_timeline_route(self) -> None:
        status, response = self.request(
            "POST", "/mcp", token=TOKEN,
            body={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": "omada_gateway_health_timeline",
                             "arguments": {"site_ref": SITE_REF,
                                           "gateway_ref": GATEWAY_REF}}})
        self.assertEqual(status, 200)
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "gateway_health_timeline")
        self.assertEqual(len(self.upstream_calls), 1)

    def test_auth_inventory_binding_fixed_24h_projection_and_privacy(self) -> None:
        route = "GET /v1/sites/{site_ref}/gateways/{gateway_ref}/health/timeline"
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == route)
        self.assertEqual(operation["support_state"], "unknown")
        self.assertEqual(operation["runtime_evidence"], [])

        status, denied = self.request("GET", self.public_path())
        self.assertEqual(status, 401)
        self.assertEqual(denied["error"], "unauthorized")
        self.assertEqual(self.upstream_calls, [])

        status, value = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertEqual(value["resource"], "gateway_health_timeline")
        self.assertEqual(value["site_ref"], SITE_REF)
        self.assertEqual(value["gateway_ref"], GATEWAY_REF)
        self.assertEqual(value["window_start_ms"], self.start_ms)
        self.assertEqual(value["window_end_ms"], self.end_ms)
        self.assertEqual(value["data"]["scores"], [
            {"time_ms": self.start_ms, "score": 83},
            {"time_ms": self.end_ms, "score": 91},
        ])
        self.assertFalse(value["partial"])
        self.assertEqual(len(self.upstream_calls), 1)
        self.assertEqual(self.upstream_calls[0][0], "GET")
        self.assertIsNone(self.upstream_calls[0][2])

        before = len(self.upstream_calls)
        for site_ref, gateway_ref in (("e" * 24, GATEWAY_REF),
                                      (OTHER_SITE_REF, GATEWAY_REF),
                                      (SITE_REF, OTHER_GATEWAY_REF)):
            status, error = self.request("GET", self.public_path(site_ref, gateway_ref), token=TOKEN)
            self.assertNotEqual(status, 200)
            self.assertEqual(len(self.upstream_calls), before)
            self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))
            self.assertNotIn(GATEWAY_MAC, json.dumps(error))

    def test_duplicate_normalized_gateway_mac_is_ambiguous_before_upstream(self) -> None:
        self.client._gateway_macs_by_site_ref[SITE_REF][OTHER_GATEWAY_REF] = "aa:bb:cc:dd:ee:ff"
        before = len(self.upstream_calls)
        status, error = self.request("GET", self.public_path(), token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(error["error"], "gateway_ref_ambiguous")
        self.assertEqual(len(self.upstream_calls), before)
        self.assertNotIn(GATEWAY_MAC, json.dumps(error))

    def test_invalid_missing_and_out_of_window_values_mark_partial_without_leaks(self) -> None:
        self.result = {"scores": [
            {"time": self.start_ms - 1, "score": 75},
            {"time": self.end_ms + 1, "score": 76},
            {"time": "private-invalid-time", "score": 77},
            {"time": self.end_ms, "score": True},
            {"time": self.end_ms, "score": None, "id": PRIVATE_MARKERS[3]},
            {"score": 80},
            {"time": self.end_ms, "score": 88, "privateText": PRIVATE_MARKERS[4]},
        ], "mac": GATEWAY_MAC, "name": PRIVATE_MARKERS[0], "ip": PRIVATE_MARKERS[1],
            "networkId": PRIVATE_MARKERS[2]}
        status, value = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertTrue(value["partial"])
        self.assertEqual(value["data"]["scores"], [
            {"time_ms": self.end_ms},
            {"time_ms": self.end_ms},
            {"time_ms": self.end_ms, "score": 88},
        ])
        rendered = json.dumps(value)
        for private in (*PRIVATE_MARKERS, GATEWAY_MAC, "privateText", "networkId"):
            self.assertNotIn(private, rendered)
            self.assertNotIn(private, self.logs.getvalue())
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == "GET /v1/sites/{site_ref}/gateways/{gateway_ref}/health/timeline")
        self.assertEqual(operation["runtime_evidence"][-1]["support_state"], "unknown")
        self.assertEqual(operation["runtime_evidence"][-1]["observation"], "response_partial")

    def test_missing_score_list_and_upstream_failure(self) -> None:
        self.result = {"private": PRIVATE_MARKERS[0]}
        status, value = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertTrue(value["partial"])
        self.assertNotIn("scores", value["data"])
        self.assertNotIn(PRIVATE_MARKERS[0], json.dumps(value))

        self.fail_upstream = True
        status, error = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_rejected")
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))

    def test_get_only_and_fixed_controller_path_query_window_allowlist(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        good = (f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/gateways/{GATEWAY_MAC}/health/timeline"
                f"?start={self.start_ms}&end={self.end_ms}")
        with patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", good, token="token")
            rejected = (
                ("POST", good), ("PUT", good), ("PATCH", good), ("DELETE", good),
                ("GET", good + "&debug=1"),
                ("GET", good.replace("/openapi/v1/ctrl/", "/openapi/v1/foreign/")),
                ("GET", good.replace("/health/timeline", "/health/other")),
                ("GET", good.replace(f"start={self.start_ms}", f"start={self.start_ms - 1}")),
                ("GET", good.replace(f"end={self.end_ms}", f"end={self.end_ms + 1}")),
            )
            for method, path in rejected:
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, token="token")

        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, _ = self.request(method, self.public_path(), token=TOKEN)
            self.assertNotEqual(status, 200)
        status, _ = self.request("GET", self.public_path() + "?debug=1", token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(self.upstream_calls, [])


if __name__ == "__main__":
    unittest.main()
