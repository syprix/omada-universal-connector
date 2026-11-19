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


TOKEN = "client-timeline-caller-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
CLIENT_REF = "c" * 24
UNKNOWN_CLIENT_REF = "d" * 24
PRIVATE_SITE_ID = "private-site-id"
PRIVATE_CLIENT_MAC = "AA-BB-CC-DD-EE-FF"
OTHER_PRIVATE_MAC = "11:22:33:44:55:66"
PRIVATE_NAME = "private-client-name"
PRIVATE_CONTENT = "private-event-content"
PRIVATE_ATTRIBUTE = "secret-ssid"


class FixedDateTime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 1, 2, 12, 0, tzinfo=tz or timezone.utc)


class ClientTimelineIntegrationTests(unittest.TestCase):
    TYPE_BY_KIND = {"connect": 0, "disconnect": 1, "roaming": 2,
                    "blocked": 3, "association": 1}

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(TOKEN)
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = PRIVATE_SITE_ID
        self.client._site_ids_by_ref[OTHER_SITE_REF] = "other-private-site-id"
        self.client._client_macs_by_site_ref[SITE_REF] = {CLIENT_REF: PRIVATE_CLIENT_MAC}
        self.client._client_macs_by_site_ref[OTHER_SITE_REF] = {UNKNOWN_CLIENT_REF: OTHER_PRIVATE_MAC}
        self.result: object = []
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
                f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/clients/{PRIVATE_CLIENT_MAC}/client-timeline")
            query = parse_qs(parsed.query, strict_parsing=True)
            self.assertEqual(set(query), {"start", "end", "type"})
            start_ms, end_ms = int(query["start"][0]), int(query["end"][0])
            self.assertEqual(end_ms - start_ms, 86_400_000)
            self.assertIn(int(query["type"][0]), self.TYPE_BY_KIND.values())
            if self.fail_upstream:
                raise OpenApiError("openapi_rejected", -1001)
            return {"result": self.result}

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
    def public_path(site_ref: str = SITE_REF, client_ref: str = CLIENT_REF,
                    kind: str = "connect") -> str:
        return f"/v1/sites/{site_ref}/clients/{client_ref}/timeline/{kind}"

    @staticmethod
    def window() -> tuple[int, int]:
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

    def test_auth_binding_fixed_window_type_map_and_privacy(self) -> None:
        operation_routes = {
            kind: f"GET /v1/sites/{{site_ref}}/clients/{{client_ref}}/timeline/{kind}"
            for kind in self.TYPE_BY_KIND
        }
        capability = self.client.capabilities()
        for operation_route in operation_routes.values():
            operation = next(item for item in capability["items"] if item["route"] == operation_route)
            self.assertEqual(operation["support_state"], "unknown")
            self.assertEqual(operation["runtime_evidence"], [])

        status, denied = self.request("GET", self.public_path())
        self.assertEqual(status, 401)
        self.assertEqual(denied["error"], "unauthorized")
        self.assertEqual(self.upstream_calls, [])

        start_ms, end_ms = self.window()
        completed_kinds: set[str] = set()
        for kind, expected_type in self.TYPE_BY_KIND.items():
            self.result = [{
                "mac": PRIVATE_CLIENT_MAC,
                "start": start_ms + 10,
                "end": end_ms - 10,
                "events": [{
                    "time": start_ms + 20,
                    "eventType": expected_type,
                    "content": PRIVATE_CONTENT,
                    "attributes": {"ssid": PRIVATE_ATTRIBUTE, "clientName": PRIVATE_NAME,
                                   "ip": "192.0.2.88", "peerMac": OTHER_PRIVATE_MAC},
                }],
            }]
            status, value = self.request("GET", self.public_path(kind=kind), token=TOKEN)
            self.assertEqual(status, 200, value)
            method, path, body = self.upstream_calls[-1]
            self.assertEqual((method, body), ("GET", None))
            parsed = urlsplit(path)
            query = parse_qs(parsed.query, strict_parsing=True)
            self.assertEqual(set(query), {"start", "end", "type"})
            self.assertEqual(int(query["start"][0]), start_ms)
            self.assertEqual(int(query["end"][0]), end_ms)
            self.assertEqual(int(query["type"][0]), expected_type)
            self.assertEqual(end_ms - start_ms, 86_400_000)
            self.assertEqual(value["resource"], "client_timeline")
            self.assertEqual(value["site_ref"], SITE_REF)
            self.assertEqual(value["client_ref"], CLIENT_REF)
            self.assertEqual(value["kind"], kind)
            self.assertEqual(value["window_start_ms"], start_ms)
            self.assertEqual(value["window_end_ms"], end_ms)
            self.assertEqual(value["data"]["sessions"], [{
                "start_ms": start_ms + 10,
                "end_ms": end_ms - 10,
                "events": [{"time_ms": start_ms + 20, "event_type": expected_type}],
            }])
            self.assertFalse(value["partial"])
            rendered = json.dumps(value)
            for private in (PRIVATE_SITE_ID, PRIVATE_CLIENT_MAC, OTHER_PRIVATE_MAC,
                            PRIVATE_NAME, PRIVATE_CONTENT, PRIVATE_ATTRIBUTE,
                            "192.0.2.88", "attributes", "content"):
                self.assertNotIn(private, rendered)
            completed_kinds.add(kind)
            capability = self.client.capabilities()
            for other_kind, route in operation_routes.items():
                other_operation = next(item for item in capability["items"]
                                       if item["route"] == route)
                evidence = other_operation["runtime_evidence"]
                if other_kind in completed_kinds:
                    self.assertEqual(evidence[-1]["support_state"], "unknown")
                    self.assertEqual(evidence[-1]["response_shape_state"],
                                     "response_shape_supported")
                    self.assertFalse(evidence[-1]["controller_response_observed"])
                else:
                    self.assertEqual(evidence, [])
                    self.assertEqual(other_operation["support_state"], "unknown")

        for private in (PRIVATE_SITE_ID, PRIVATE_CLIENT_MAC, PRIVATE_NAME,
                        PRIVATE_CONTENT, PRIVATE_ATTRIBUTE):
            self.assertNotIn(private, self.logs.getvalue())

    def test_unknown_site_and_cross_site_or_unknown_client_do_not_read(self) -> None:
        for site_ref, client_ref, expected_error in (
                (OTHER_SITE_REF, CLIENT_REF, "client_ref_unknown"),
                (SITE_REF, UNKNOWN_CLIENT_REF, "client_ref_unknown"),
                ("e" * 24, CLIENT_REF, "site_ref_unknown")):
            status, value = self.request("GET", self.public_path(site_ref, client_ref), token=TOKEN)
            self.assertEqual(status, 502)
            self.assertEqual(value["error"], expected_error)
            self.assertEqual(self.upstream_calls, [])
            self.assertNotIn(PRIVATE_SITE_ID, json.dumps(value))

    def test_bad_unknown_and_out_of_window_rows_are_partial_and_redacted(self) -> None:
        start_ms, end_ms = self.window()
        self.result = [
            {"mac": PRIVATE_CLIENT_MAC, "start": start_ms - 1,
             "end": end_ms, "events": [{"time": start_ms, "eventType": 0}]},
            {"mac": PRIVATE_CLIENT_MAC, "start": "private-invalid-start",
             "end": end_ms, "events": [{"time": end_ms + 1, "eventType": 2}]},
            {"mac": PRIVATE_CLIENT_MAC, "start": end_ms,
             "end": end_ms + 1, "events": [{"time": end_ms, "eventType": 999,
                                              "content": PRIVATE_CONTENT}]},
            {"mac": PRIVATE_CLIENT_MAC, "start": end_ms,
             "end": end_ms, "events": [{"eventType": 1, "content": PRIVATE_CONTENT}]},
            {"mac": PRIVATE_CLIENT_MAC, "start": end_ms, "end": end_ms,
             "events": [{"time": end_ms, "eventType": 3, "attributes": {"ssid": PRIVATE_ATTRIBUTE}}],
             "unknown": PRIVATE_NAME},
        ]
        status, value = self.request("GET", self.public_path(kind="disconnect"), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertTrue(value["partial"])
        rendered = json.dumps(value)
        for private in (PRIVATE_SITE_ID, PRIVATE_CLIENT_MAC, PRIVATE_NAME,
                        PRIVATE_CONTENT, PRIVATE_ATTRIBUTE, "private-invalid-start",
                        "attributes"):
            self.assertNotIn(private, rendered)

        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == "GET /v1/sites/{site_ref}/clients/{client_ref}/timeline/disconnect")
        evidence = operation["runtime_evidence"][-1]
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["observation"], "response_partial")

    def test_session_mac_mismatch_is_omitted_and_missing_mac_is_partial(self) -> None:
        start_ms, end_ms = self.window()
        self.result = [
            {"mac": PRIVATE_CLIENT_MAC, "start": start_ms + 1, "end": end_ms,
             "events": [{"time": start_ms + 2, "eventType": 0}]},
            {"mac": OTHER_PRIVATE_MAC, "start": start_ms + 10, "end": end_ms,
             "events": [{"time": start_ms + 11, "eventType": 2}]},
            {"start": start_ms + 20, "end": end_ms,
             "events": [{"time": start_ms + 21, "eventType": 3}]},
        ]
        status, value = self.request("GET", self.public_path(kind="connect"), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertTrue(value["partial"])
        returned_starts = [session.get("start_ms") for session in value["data"]["sessions"]]
        self.assertNotIn(start_ms + 10, returned_starts)
        self.assertNotIn(PRIVATE_CLIENT_MAC, json.dumps(value))
        self.assertNotIn(OTHER_PRIVATE_MAC, json.dumps(value))
        self.assertIn("session_identity_mismatch", value["omitted_fields"])

    def test_controller_failure_and_complete_capability(self) -> None:
        start_ms, _ = self.window()
        self.result = [{"mac": PRIVATE_CLIENT_MAC, "start": start_ms,
                        "end": start_ms + 1, "events": [
            {"time": start_ms, "eventType": 0}]}]
        status, value = self.request("GET", self.public_path(kind="connect"), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertFalse(value["partial"])
        operation_route = "GET /v1/sites/{site_ref}/clients/{client_ref}/timeline/connect"
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == operation_route)
        evidence = operation["runtime_evidence"][-1]
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["response_shape_state"], "response_shape_supported")
        self.assertFalse(evidence["controller_response_observed"])

        self.fail_upstream = True
        status, error = self.request("GET", self.public_path(kind="connect"), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_rejected")
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == operation_route)
        self.assertEqual(operation["runtime_evidence"][-1]["support_state"], "unknown")
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))

    def test_public_and_upstream_allowlists_reject_other_paths_methods_queries_types(self) -> None:
        for kind in ("unknown", "CONNECT", "Association"):
            status, _ = self.request("GET", self.public_path(kind=kind), token=TOKEN)
            self.assertNotEqual(status, 200)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, _ = self.request(method, self.public_path(kind="connect"), token=TOKEN)
            self.assertNotEqual(status, 200)
        status, _ = self.request("GET", self.public_path(kind="connect") + "?start=1", token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(self.upstream_calls, [])

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        start_ms, end_ms = self.window()
        good = (f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/clients/{PRIVATE_CLIENT_MAC}/client-timeline"
                f"?start={start_ms}&end={end_ms}&type=0")
        with patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", good, token="token")
            for method, path in (
                    ("POST", good), ("PATCH", good), ("DELETE", good),
                    ("GET", good + "&debug=1"),
                    ("GET", good.replace("/openapi/v1/ctrl/", "/openapi/v1/foreign/")),
                    ("GET", good.replace("type=0", "type=4")),
                    ("GET", good.replace(f"start={start_ms}", f"start={start_ms - 1}")),
                    ("GET", good.replace(f"end={end_ms}", f"end={end_ms + 1}")),
                    ("GET", good.replace("client-timeline", "client-history"))):
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, token="token")


if __name__ == "__main__":
    unittest.main()
