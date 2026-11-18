from __future__ import annotations

import builtins
import io
import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


TOKEN = "client-signal-distribution-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
PRIVATE_SITE_ID = "private-site-id"
PRIVATE_NAME = "private-client-name"
PRIVATE_MAC = "AA-BB-CC-DD-EE-FF"
PRIVATE_IP = "192.0.2.71"
CATEGORIES = ("poorSignal", "weakSignal", "averageSignal", "stableSignal", "strongSignal")
FIELDS = ("totalClients", "clientsPercent", "clients2g", "clients5g", "clients6g")


def documented_result() -> dict[str, object]:
    return {
        category: {
            "totalClients": index + 10,
            "clientsPercent": index * 17,
            "clients2g": index + 1,
            "clients5g": index + 2,
            "clients6g": index + 3,
        }
        for index, category in enumerate(CATEGORIES)
    }


class ClientSignalDistributionIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as handle:
            handle.write(TOKEN)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = PRIVATE_SITE_ID
        self.result: object = documented_result()
        self.fail_upstream = False
        self.transport_calls: list[tuple[str, str, bytes | None]] = []

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.transport_calls.append((method, path, body))
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(token, "synthetic-upstream-token")
            self.assertEqual(path, self._upstream_path())
            if self.fail_upstream:
                raise OpenApiError("openapi_rejected", -1001)
            return {"result": json.loads(json.dumps(self.result))}

        self.transport_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.transport_patch.start()
        self.access_patch = patch.object(
            self.client, "_access_token", return_value="synthetic-upstream-token")
        self.access_patch.start()
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
        self.access_patch.stop()
        self.transport_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def _upstream_path(controller_id: str = "ctrl") -> str:
        return (f"/openapi/v1/{controller_id}/sites/{PRIVATE_SITE_ID}/"
                "dashboard/client-signal-distribution")

    @staticmethod
    def _public_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/wifi/client-signal-distribution"

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

    def test_auth_fixed_get_five_categories_five_int32_fields_and_redaction(self) -> None:
        route = "GET /v1/sites/{site_ref}/wifi/client-signal-distribution"
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == route)
        self.assertEqual(operation["support_state"], "unknown")
        self.assertEqual(operation["runtime_evidence"], [])

        status, unauth = self.request("GET", self._public_path())
        self.assertEqual(status, 401)
        self.assertEqual(unauth["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        status, value = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertEqual(value["resource"], "client_signal_distribution")
        self.assertEqual(set(value["data"]), set(CATEGORIES))
        self.assertEqual(value["data"], documented_result())
        for category in CATEGORIES:
            self.assertEqual(set(value["data"][category]), set(FIELDS))
            self.assertTrue(all(type(value["data"][category][field]) is int for field in FIELDS))
        self.assertFalse(value["partial"])
        self.assertEqual(self.transport_calls, [("GET", self._upstream_path(), None)])

        # The documented integer field is retained as an integer; no scale or
        # percentage conversion is inferred by this HTTP adapter.
        self.assertEqual(value["data"]["weakSignal"]["clientsPercent"], 17)

        self.result = {
            **documented_result(), "name": PRIVATE_NAME, "mac": PRIVATE_MAC,
            "ip": PRIVATE_IP, "rawLabel": "private-raw-label",
        }
        status, redacted = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 200, redacted)
        self.assertTrue(redacted["partial"])
        rendered = json.dumps(redacted)
        for private in (PRIVATE_SITE_ID, PRIVATE_NAME, PRIVATE_MAC, PRIVATE_IP, "private-raw-label"):
            self.assertNotIn(private, rendered)
            self.assertNotIn(private, self.logs.getvalue())

    def test_unknown_site_and_partial_fields_leave_capability_unknown(self) -> None:
        status, error = self.request("GET", self._public_path(OTHER_SITE_REF), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "site_ref_unknown")
        self.assertEqual(self.transport_calls, [])
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))

        partial_fixtures = (
            {key: value for key, value in documented_result().items() if key != "weakSignal"},
            {**documented_result(), "poorSignal": {
                **documented_result()["poorSignal"], "clients2g": None}},
            {**documented_result(), "averageSignal": {
                **documented_result()["averageSignal"], "clientsPercent": True}},
            {**documented_result(), "strongSignal": {
                **documented_result()["strongSignal"], "privateMarker": PRIVATE_NAME}},
        )
        route = "GET /v1/sites/{site_ref}/wifi/client-signal-distribution"
        for raw in partial_fixtures:
            with self.subTest(raw=raw):
                self.result = raw
                status, value = self.request("GET", self._public_path(), token=TOKEN)
                self.assertEqual(status, 200, value)
                self.assertTrue(value["partial"])
                rendered = json.dumps(value)
                self.assertNotIn(PRIVATE_NAME, rendered)
                self.assertNotIn("privateMarker", rendered)
                operation = next(item for item in self.client.capabilities()["items"]
                                 if item["route"] == route)
                evidence = operation["runtime_evidence"][-1]
                self.assertEqual(evidence["support_state"], "unknown")
                self.assertEqual(evidence["observation"], "response_partial")
                self.assertEqual(evidence["hardware_support_state"], "unknown")
                self.assertEqual(evidence["firmware_support_state"], "unknown")

    def test_invalid_result_shape_and_controller_failure_are_redacted(self) -> None:
        self.result = None
        status, error = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_response_invalid")
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))

        self.result = documented_result()
        self.fail_upstream = True
        status, error = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_rejected")
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))

    def test_only_fixed_controller_get_path_and_no_public_methods_or_queries(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        valid = self._upstream_path()
        with patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", valid, token="token")
            rejected = (
                ("POST", valid), ("PUT", valid), ("PATCH", valid), ("DELETE", valid),
                ("GET", valid + "?raw=true"),
                ("GET", self._upstream_path("foreign-controller")),
                ("GET", valid.replace("/client-signal-distribution", "/clients")),
            )
            for method, path in rejected:
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, token="token")

        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, _ = self.request(method, self._public_path(), token=TOKEN)
            self.assertNotEqual(status, 200)
        status, _ = self.request("GET", self._public_path() + "?debug=1", token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(self.transport_calls, [])


if __name__ == "__main__":
    unittest.main()
