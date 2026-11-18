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


TOKEN = "client-health-caller-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
PRIVATE_SITE_ID = "private-site-id"
OTHER_PRIVATE_SITE_ID = "other-private-site-id"
PRIVATE_CLIENT_MAC = "AA-BB-CC-DD-EE-FF"
OTHER_CLIENT_MAC = "11:22:33:44:55:66"
PRIVATE_NAME = "private-client-name"
PRIVATE_IP = "192.0.2.81"
PRIVATE_NOTE = "private-controller-note"


class FixedDateTime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 1, 2, 12, 0, tzinfo=tz or timezone.utc)


class ClientHealthTimelineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(TOKEN)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.site_rows = [{"siteId": PRIVATE_SITE_ID, "name": PRIVATE_NAME},
                          {"siteId": OTHER_PRIVATE_SITE_ID, "name": "other-private-site"}]
        self.client_rows = [{"mac": PRIVATE_CLIENT_MAC, "name": PRIVATE_NAME,
                             "ip": PRIVATE_IP, "wireless": True, "rssi": -55,
                             "snr": 30, "channel": 36, "active": True}]
        self.health_result: object = {"scores": [{"time": 0, "score": 72}]}
        self.upstream_calls: list[tuple[str, str, bytes | None]] = []
        self.fail_health = False

        def page(data: list[object], query: dict[str, list[str]]) -> dict[str, object]:
            page_no = int(query["page"][0])
            size = int(query["pageSize"][0])
            start = (page_no - 1) * size
            selected = data[start:start + size]
            return {"result": {"data": selected, "totalRows": len(data),
                               "currentPage": page_no, "currentSize": len(selected)}}

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.upstream_calls.append((method, path, body))
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(token, "synthetic-upstream-token")
            parsed = urlsplit(path)
            if parsed.path == "/openapi/v1/ctrl/sites":
                query = parse_qs(parsed.query, strict_parsing=True)
                self.assertEqual(set(query), {"page", "pageSize"})
                return page(self.site_rows, query)
            if parsed.path == f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/clients":
                query = parse_qs(parsed.query, strict_parsing=True)
                self.assertEqual(set(query), {"page", "pageSize"})
                return page(self.client_rows, query)
            if parsed.path == f"/openapi/v1/ctrl/sites/{OTHER_PRIVATE_SITE_ID}/clients":
                query = parse_qs(parsed.query, strict_parsing=True)
                self.assertEqual(set(query), {"page", "pageSize"})
                return page([{"mac": OTHER_CLIENT_MAC, "wireless": True}], query)
            self.assertEqual(parsed.path,
                f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/clients/{PRIVATE_CLIENT_MAC}/health/timeline")
            query = parse_qs(parsed.query, strict_parsing=True)
            self.assertEqual(set(query), {"start", "end"})
            start_ms, end_ms = int(query["start"][0]), int(query["end"][0])
            self.assertEqual(end_ms - start_ms, 86_400_000)
            if self.fail_health:
                raise OpenApiError("openapi_rejected", -1001)
            return {"result": self.health_result}

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

    def inventory(self, site_ref: str = SITE_REF) -> tuple[str, str]:
        status, sites = self.request("GET", "/v1/sites", token=TOKEN)
        self.assertEqual(status, 200, sites)
        self.assertEqual(sites["count"], 2)
        self.site_refs = {row["site_ref"] for row in sites["items"]}
        site_ref = sites["items"][0]["site_ref"] if site_ref == SITE_REF else sites["items"][1]["site_ref"]
        status, clients = self.request("GET", f"/v1/sites/{site_ref}/clients", token=TOKEN)
        self.assertEqual(status, 200, clients)
        self.assertEqual(clients["resource"], "clients")
        self.assertEqual(clients["count"], 1)
        return site_ref, clients["items"][0]["client_ref"]

    @staticmethod
    def window() -> tuple[int, int]:
        end_ms = int(FixedDateTime.now(timezone.utc).timestamp() * 1000)
        return end_ms - 86_400_000, end_ms

    def test_auth_fresh_inventory_binding_fixed_window_and_redacted_scores(self) -> None:
        status, denied = self.request("GET", f"/v1/sites/{SITE_REF}/clients/{'c' * 24}/health/timeline")
        self.assertEqual(status, 401)
        self.assertEqual(denied["error"], "unauthorized")
        self.assertEqual(self.upstream_calls, [])

        site_ref, client_ref = self.inventory()
        start_ms, end_ms = self.window()
        self.health_result = {"scores": [
            {"time": start_ms + 1, "score": 72},
            {"time": end_ms, "score": -(2**31), "name": PRIVATE_NAME,
             "mac": PRIVATE_CLIENT_MAC, "ip": PRIVATE_IP, "note": PRIVATE_NOTE},
        ], "private": PRIVATE_NOTE}
        route = f"/v1/sites/{site_ref}/clients/{client_ref}/health/timeline"
        status, value = self.request("GET", route, token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertEqual(value["resource"], "client_health_timeline")
        self.assertEqual(value["site_ref"], site_ref)
        self.assertEqual(value["client_ref"], client_ref)
        self.assertEqual(value["window_start_ms"], start_ms)
        self.assertEqual(value["window_end_ms"], end_ms)
        self.assertEqual(value["data"]["scores"], [
            {"time_ms": start_ms + 1, "score": 72},
            {"time_ms": end_ms, "score": -(2**31)},
        ])
        self.assertTrue(value["partial"])
        calls = self.upstream_calls
        self.assertEqual(len(calls), 3)
        health_method, health_path, health_body = calls[-1]
        self.assertEqual((health_method, health_body), ("GET", None))
        parsed = urlsplit(health_path)
        self.assertEqual(parsed.path,
            f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/clients/{PRIVATE_CLIENT_MAC}/health/timeline")
        query = parse_qs(parsed.query, strict_parsing=True)
        self.assertEqual(set(query), {"start", "end"})
        self.assertEqual((int(query["start"][0]), int(query["end"][0])), (start_ms, end_ms))
        rendered = json.dumps(value)
        for secret in (PRIVATE_SITE_ID, PRIVATE_CLIENT_MAC, OTHER_CLIENT_MAC,
                       PRIVATE_NAME, PRIVATE_IP, PRIVATE_NOTE, "private"):
            self.assertNotIn(secret, rendered)
            self.assertNotIn(secret, self.logs.getvalue())

    def test_wrong_site_and_stale_client_reference_fail_before_health_request(self) -> None:
        site_ref, client_ref = self.inventory()
        other_ref = next(ref for ref in self.site_refs if ref != site_ref)
        status, other_clients = self.request("GET", f"/v1/sites/{other_ref}/clients", token=TOKEN)
        self.assertEqual(status, 200, other_clients)
        self.assertNotEqual(client_ref, other_clients["items"][0]["client_ref"])
        before = len(self.upstream_calls)
        status, value = self.request(
            "GET", f"/v1/sites/{other_ref}/clients/{client_ref}/health/timeline", token=TOKEN)
        self.assertIn(status, (400, 404, 502))
        self.assertNotIn("health/timeline", " ".join(call[1] for call in self.upstream_calls[before:]))

        status, refreshed = self.request("GET", f"/v1/sites/{site_ref}/clients", token=TOKEN)
        self.assertEqual(status, 200, refreshed)
        fresh_ref = refreshed["items"][0]["client_ref"]
        self.assertNotEqual(client_ref, fresh_ref)
        before = len(self.upstream_calls)
        status, stale = self.request(
            "GET", f"/v1/sites/{site_ref}/clients/{client_ref}/health/timeline", token=TOKEN)
        self.assertIn(status, (400, 404, 502))
        self.assertNotIn("health/timeline", " ".join(call[1] for call in self.upstream_calls[before:]))
        self.assertNotIn(PRIVATE_CLIENT_MAC, json.dumps(stale))

    def test_invalid_and_missing_points_are_partial_without_echoing_payload(self) -> None:
        site_ref, client_ref = self.inventory()
        start_ms, end_ms = self.window()
        self.health_result = {"scores": [
            {"time": start_ms - 1, "score": 10},
            {"time": end_ms + 1, "score": 11},
            {"time": "malicious-private-time", "score": 12},
            {"time": end_ms, "score": True},
            {"score": 14},
            {"time": end_ms, "score": None},
            {"time": end_ms, "score": 2**31},
        ], "incident": PRIVATE_NOTE, "ssid": PRIVATE_NAME}
        status, value = self.request(
            "GET", f"/v1/sites/{site_ref}/clients/{client_ref}/health/timeline", token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertTrue(value["partial"])
        self.assertEqual(value["data"]["scores"], [
            {"time_ms": end_ms}, {"time_ms": end_ms}, {"time_ms": end_ms},
        ])
        for secret in ("malicious-private-time", PRIVATE_NOTE, PRIVATE_NAME, "incident", "ssid"):
            self.assertNotIn(secret, json.dumps(value))

    def test_missing_scores_and_upstream_error_are_sanitized(self) -> None:
        site_ref, client_ref = self.inventory()
        self.health_result = {"private": PRIVATE_NOTE}
        route = f"/v1/sites/{site_ref}/clients/{client_ref}/health/timeline"
        status, missing = self.request("GET", route, token=TOKEN)
        self.assertEqual(status, 200, missing)
        self.assertTrue(missing["partial"])
        self.assertNotIn("scores", missing.get("data", {}))
        self.assertNotIn(PRIVATE_NOTE, json.dumps(missing))

        self.fail_health = True
        status, failed = self.request("GET", route, token=TOKEN)
        self.assertEqual(status, 502)
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(failed))
        self.assertNotIn(PRIVATE_CLIENT_MAC, json.dumps(failed))
        self.assertNotIn(PRIVATE_NOTE, json.dumps(failed))

    def test_point_bound_rejects_oversized_response_without_echo(self) -> None:
        site_ref, client_ref = self.inventory()
        start_ms, end_ms = self.window()
        self.health_result = {
            "scores": [{"time": start_ms, "score": 1}] * 257,
            "private": PRIVATE_NOTE,
        }
        status, value = self.request(
            "GET", f"/v1/sites/{site_ref}/clients/{client_ref}/health/timeline", token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(value["error"], "openapi_response_invalid")
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(value))
        self.assertNotIn(PRIVATE_CLIENT_MAC, json.dumps(value))
        self.assertNotIn(PRIVATE_NOTE, json.dumps(value))

    def test_fixed_get_route_rejects_queries_writes_and_invalid_references(self) -> None:
        site_ref, client_ref = self.inventory()
        base = f"/v1/sites/{site_ref}/clients/{client_ref}/health/timeline"
        before = len(self.upstream_calls)
        status, _ = self.request("GET", base + "?start=1&end=2", token=TOKEN)
        self.assertIn(status, (400, 404))
        status, _ = self.request("POST", base, token=TOKEN)
        self.assertNotEqual(status, 200)
        status, _ = self.request("GET", f"/v1/sites/{'f' * 24}/clients/{client_ref}/health/timeline", token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(len(self.upstream_calls), before)

    def test_capability_evidence_is_route_specific_and_partial_is_not_live_support(self) -> None:
        site_ref, client_ref = self.inventory()
        route_name = "GET /v1/sites/{site_ref}/clients/{client_ref}/health/timeline"
        before = next(item for item in self.client.capabilities()["items"] if item["route"] == route_name)
        self.assertEqual(before["support_state"], "unknown")
        start_ms, end_ms = self.window()
        self.health_result = {"scores": [{"time": start_ms, "score": 72}]}
        status, complete = self.request(
            "GET", f"/v1/sites/{site_ref}/clients/{client_ref}/health/timeline", token=TOKEN)
        self.assertEqual(status, 200, complete)
        self.assertFalse(complete["partial"])
        entry = next(item for item in self.client.capabilities()["items"] if item["route"] == route_name)
        evidence = entry["runtime_evidence"][-1]
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["response_shape_state"], "response_shape_supported")
        self.assertFalse(evidence["controller_response_observed"])

        self.health_result = {"scores": [{"time": end_ms + 1, "score": 88}]}
        status, partial = self.request(
            "GET", f"/v1/sites/{site_ref}/clients/{client_ref}/health/timeline", token=TOKEN)
        self.assertEqual(status, 200, partial)
        self.assertTrue(partial["partial"])
        entry = next(item for item in self.client.capabilities()["items"] if item["route"] == route_name)
        self.assertEqual(entry["runtime_evidence"][-1]["support_state"], "unknown")


if __name__ == "__main__":
    unittest.main()
