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


TOKEN = "ap-timeline-caller-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
AP_REF = "c" * 24
OTHER_AP_REF = "d" * 24
PRIVATE_SITE_ID = "site-private-id"
PRIVATE_AP_MAC = "AA-BB-CC-DD-EE-FF"
PRIVATE_NAME = "private-office-ap"
PRIVATE_IP = "192.0.2.45"


class FixedDateTime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 1, 2, 12, 0, tzinfo=tz or timezone.utc)


class ApHealthTimelineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(TOKEN)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = PRIVATE_SITE_ID
        self.client._device_macs_by_site_ref[SITE_REF] = {AP_REF: PRIVATE_AP_MAC}
        self.upstream_result: object = {"scores": [{"time": 0, "score": 75}]}
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
                f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/eaps/{PRIVATE_AP_MAC}/health/timeline")
            query = parse_qs(parsed.query, strict_parsing=True)
            self.assertEqual(set(query), {"start", "end"})
            start_ms, end_ms = int(query["start"][0]), int(query["end"][0])
            self.assertEqual(end_ms - start_ms, 86_400_000)
            if self.fail_upstream:
                raise OpenApiError("openapi_rejected", -1001)
            return {"result": self.upstream_result}

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
    def public_path(site_ref: str = SITE_REF, ap_ref: str = AP_REF) -> str:
        return f"/v1/sites/{site_ref}/aps/{ap_ref}/health/timeline"

    @staticmethod
    def expected_window() -> tuple[int, int]:
        end_ms = int(FixedDateTime.now(timezone.utc).timestamp() * 1000)
        return end_ms - 86_400_000, end_ms

    def request(self, method: str, path: str, *, token: str | None = None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + token} if token is not None else {}
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = {}
        status = response.status
        connection.close()
        return status, value

    def test_auth_site_ap_binding_fixed_24h_and_redacted_projection(self) -> None:
        route = self.public_path()
        operation_route = "GET /v1/sites/{site_ref}/aps/{device_ref}/health/timeline"
        capability = self.client.capabilities()
        operation = next(item for item in capability["items"] if item["route"] == operation_route)
        self.assertEqual(operation["support_state"], "unknown")
        self.assertEqual(operation["runtime_evidence"], [])

        status, denied = self.request("GET", route)
        self.assertEqual(status, 401)
        self.assertEqual(denied["error"], "unauthorized")
        self.assertEqual(self.upstream_calls, [])

        start_ms, end_ms = self.expected_window()
        self.upstream_result = {"scores": [
            {"time": start_ms + 1, "score": 75},
            {"time": end_ms, "score": 81, "name": PRIVATE_NAME,
             "mac": PRIVATE_AP_MAC, "ip": PRIVATE_IP, "rawId": "private-score-id"},
        ], "private": "private-controller-payload"}
        status, value = self.request("GET", route, token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertEqual(len(self.upstream_calls), 1)
        method, path, body = self.upstream_calls[0]
        self.assertEqual(method, "GET")
        self.assertIsNone(body)
        parsed = urlsplit(path)
        query = parse_qs(parsed.query, strict_parsing=True)
        self.assertEqual(set(query), {"start", "end"})
        self.assertEqual(int(query["start"][0]), start_ms)
        self.assertEqual(int(query["end"][0]), end_ms)
        self.assertEqual(value["resource"], "ap_health_timeline")
        self.assertEqual(value["site_ref"], SITE_REF)
        self.assertEqual(value["device_ref"], AP_REF)
        self.assertEqual(value["window_start_ms"], start_ms)
        self.assertEqual(value["window_end_ms"], end_ms)
        self.assertEqual(value["data"]["scores"], [
            {"time_ms": start_ms + 1, "score": 75},
            {"time_ms": end_ms, "score": 81},
        ])
        self.assertTrue(value["partial"])
        rendered = json.dumps(value)
        for private in (PRIVATE_SITE_ID, PRIVATE_AP_MAC, PRIVATE_NAME, PRIVATE_IP,
                        "private-score-id", "private-controller-payload"):
            self.assertNotIn(private, rendered)
        for private in (PRIVATE_SITE_ID, PRIVATE_AP_MAC, PRIVATE_NAME, PRIVATE_IP):
            self.assertNotIn(private, self.logs.getvalue())

    def test_unknown_site_and_cross_site_or_unknown_ap_ref_fail_before_upstream(self) -> None:
        for site_ref, ap_ref, error in (
                (OTHER_SITE_REF, AP_REF, "site_ref_unknown"),
                (SITE_REF, OTHER_AP_REF, "device_ref_unknown"),
                ("g" * 24, AP_REF, "site_ref_invalid")):
            with self.subTest(site_ref=site_ref, ap_ref=ap_ref):
                status, value = self.request("GET", self.public_path(site_ref, ap_ref), token=TOKEN)
                if site_ref == "g" * 24:
                    self.assertEqual(status, 404)
                else:
                    self.assertEqual(status, 502)
                    self.assertEqual(value["error"], error)
                self.assertEqual(self.upstream_calls, [])
                self.assertNotIn(PRIVATE_SITE_ID, json.dumps(value))

    def test_partial_invalid_out_of_window_and_missing_values_are_redacted(self) -> None:
        start_ms, end_ms = self.expected_window()
        self.upstream_result = {"scores": [
            {"time": start_ms - 1, "score": 77},
            {"time": "bad-private-time", "score": 88},
            {"time": end_ms, "score": True},
            {"time": end_ms, "score": None},
            {"score": 95},
            {"time": end_ms, "score": 90, "ssid": "private-ssid"},
        ]}
        status, value = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertTrue(value["partial"])
        scores = value["data"]["scores"]
        self.assertTrue(all(row.get("time_ms") == end_ms for row in scores if "time_ms" in row))
        self.assertNotIn("bad-private-time", json.dumps(value))
        self.assertNotIn("private-ssid", json.dumps(value))
        self.assertNotIn("ssid", json.dumps(value))

        capability = self.client.capabilities()
        operation = next(item for item in capability["items"]
                         if item["route"] == "GET /v1/sites/{site_ref}/aps/{device_ref}/health/timeline")
        evidence = operation["runtime_evidence"][-1]
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["observation"], "response_partial")

    def test_missing_score_list_is_partial_and_non_object_result_fails_closed(self) -> None:
        self.upstream_result = {"private": PRIVATE_NAME}
        status, missing = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 200, missing)
        self.assertTrue(missing["partial"])
        self.assertNotIn("scores", missing["data"])
        self.assertNotIn(PRIVATE_NAME, json.dumps(missing))

        self.upstream_result = ["malformed-private-payload"]
        status, error = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_response_invalid")
        self.assertNotIn("malformed-private-payload", json.dumps(error))
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))

    def test_complete_projection_updates_capability_but_upstream_failure_stays_unknown(self) -> None:
        start_ms, end_ms = self.expected_window()
        self.upstream_result = {"scores": [{"time": start_ms, "score": 92}]}
        status, value = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertFalse(value["partial"])
        operation_route = "GET /v1/sites/{site_ref}/aps/{device_ref}/health/timeline"
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == operation_route)
        evidence = operation["runtime_evidence"][-1]
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["response_shape_state"], "response_shape_supported")
        self.assertFalse(evidence["controller_response_observed"])
        self.assertEqual(evidence["target_ref"], SITE_REF + ":" + AP_REF)

        self.fail_upstream = True
        status, error = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_rejected")
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == operation_route)
        self.assertEqual(operation["runtime_evidence"][-1]["support_state"], "unknown")
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))

    def test_public_route_rejects_other_methods_and_query_strings(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, _ = self.request(method, self.public_path(), token=TOKEN)
            self.assertNotEqual(status, 200)
        status, _ = self.request("GET", self.public_path() + "?debug=1", token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(self.upstream_calls, [])

    def test_upstream_allowlist_is_fixed_to_controller_route_and_exact_24h_query(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        start_ms, end_ms = self.expected_window()
        good = (f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/eaps/{PRIVATE_AP_MAC}/health/timeline"
                f"?start={start_ms}&end={end_ms}")
        with patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", good, token="token")
            invalid = (
                ("POST", good), ("PUT", good), ("PATCH", good), ("DELETE", good),
                ("GET", good + "&debug=1"),
                ("GET", good.replace("/openapi/v1/ctrl/", "/openapi/v1/foreign/")),
                ("GET", good.replace("/health/timeline", "/health/other")),
                ("GET", good.replace(f"start={start_ms}", f"start={start_ms - 1}")),
                ("GET", good.replace(f"end={end_ms}", f"end={end_ms + 1}")),
                ("GET", good.replace("/eaps/", "/aps/")),
            )
            for method, path in invalid:
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, token="token")


if __name__ == "__main__":
    unittest.main()
