from __future__ import annotations

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


TOKEN = "channel-dashboard-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
SITE_ID = "private-site-id"
PRIVATE_LABEL = "private-dashboard-label"
PRIVATE_MAC = "AA:BB:CC:DD:EE:FF"
PRIVATE_ID = "private-raw-id"


def documented_result() -> dict[str, object]:
    return {
        "2g channel stat": [
            {"channel": 1, "apNum": 2, "clientNum": 9, "channelUtilization": 34.5},
        ],
        "5g channel stat": [
            {"channel": 36, "apNum": 3, "clientNum": 11, "channelUtilization": 52.0},
        ],
        "6g channel stat": [
            {"channel": 5, "apNum": 1, "clientNum": 2, "channelUtilization": None},
        ],
    }


class ChannelDashboardIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as handle:
            handle.write(TOKEN)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = SITE_ID
        self.result: object = documented_result()
        self.fail_upstream = False
        self.transport_calls: list[tuple[str, str, bytes | None]] = []

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.transport_calls.append((method, path, body))
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(path, self._upstream_path())
            self.assertEqual(token, "synthetic-upstream-token")
            if self.fail_upstream:
                raise OpenApiError("openapi_rejected", -1001)
            return {"result": self.result}

        self.transport_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.transport_patch.start()
        self.access_patch = patch.object(
            self.client, "_access_token", return_value="synthetic-upstream-token")
        self.access_patch.start()
        self.env_patch = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": self.token_file})
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.client_patch.stop()
        self.env_patch.stop()
        self.access_patch.stop()
        self.transport_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def _upstream_path(controller_id: str = "ctrl") -> str:
        return f"/openapi/v1/{controller_id}/sites/{SITE_ID}/dashboard/channels"

    @staticmethod
    def _public_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/wifi/channels"

    def request(self, method: str, path: str, *, token: str | None = None) -> tuple[int, dict[str, object]]:
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

    def test_auth_fixed_upstream_redacted_aggregate_and_capability(self) -> None:
        route = self._public_path()
        initial = self.client.capabilities()
        initial_operation = next(item for item in initial["items"]
                                 if item["route"] == "GET /v1/sites/{site_ref}/wifi/channels")
        self.assertEqual(initial_operation["support_state"], "unknown")
        self.assertEqual(initial_operation["runtime_evidence"], [])

        status, unauthorized = self.request("GET", route)
        self.assertEqual(status, 401)
        self.assertEqual(unauthorized["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        status, value = self.request("GET", route, token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertEqual(self.transport_calls, [("GET", self._upstream_path(), None)])
        self.assertEqual(value["resource"], "site_dashboard_channels")
        bands = value["data"]["bands"]
        self.assertEqual(bands["2g"], [{
            "channel": 1, "ap_count": 2, "client_count": 9,
            "utilization_percent": 34.5,
        }])
        self.assertEqual(bands["5g"], [{
            "channel": 36, "ap_count": 3, "client_count": 11,
            "utilization_percent": 52.0,
        }])
        self.assertEqual(bands["6g"], [{
            "channel": 5, "ap_count": 1, "client_count": 2,
            "utilization_percent": None,
        }])
        self.assertFalse(value["partial"])

        cap = self.client.capabilities()
        operation = next(item for item in cap["items"]
                         if item["route"] == "GET /v1/sites/{site_ref}/wifi/channels")
        self.assertEqual(operation["implementation_state"], "implemented")
        self.assertEqual(operation["runtime_evidence"][0]["result"], "success")
        self.assertEqual(operation["runtime_evidence"][0]["target_ref"], SITE_REF)
        self.assertEqual(operation["runtime_evidence"][0]["permission_state"], "unknown")
        self.assertFalse(operation["runtime_evidence"][0]["controller_response_observed"])

        rendered = json.dumps(value)
        for private in (SITE_ID, PRIVATE_LABEL, PRIVATE_MAC, PRIVATE_ID):
            self.assertNotIn(private, rendered)

    def test_null_utilization_is_documented_no_data_and_unknown_fields_are_partial(self) -> None:
        result = documented_result()
        result["2g channel stat"][0].update({"name": PRIVATE_LABEL, "mac": PRIVATE_MAC,
                                             "rawId": PRIVATE_ID})
        self.result = result
        status, value = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertIsNone(value["data"]["bands"]["6g"][0]["utilization_percent"])
        self.assertTrue(value["partial"])
        rendered = json.dumps(value)
        for private in (PRIVATE_LABEL, PRIVATE_MAC, PRIVATE_ID):
            self.assertNotIn(private, rendered)

    def test_missing_invalid_and_null_documented_fields_are_partial_or_unknown(self) -> None:
        fixtures = []
        missing_band = documented_result()
        del missing_band["5g channel stat"]
        fixtures.append(missing_band)

        missing_field = documented_result()
        del missing_field["2g channel stat"][0]["clientNum"]
        fixtures.append(missing_field)

        invalid_count = documented_result()
        invalid_count["2g channel stat"][0]["apNum"] = True
        fixtures.append(invalid_count)

        invalid_util = documented_result()
        invalid_util["2g channel stat"][0]["channelUtilization"] = "private-invalid-value"
        fixtures.append(invalid_util)

        invalid_band = documented_result()
        invalid_band["5g channel stat"] = None
        fixtures.append(invalid_band)

        for raw in fixtures:
            with self.subTest(raw=raw):
                self.result = raw
                status, value = self.request("GET", self._public_path(), token=TOKEN)
                self.assertEqual(status, 200, value)
                self.assertTrue(value["partial"])
                self.assertNotIn("private-invalid-value", json.dumps(value))

    def test_unknown_and_malformed_site_refs_fail_before_upstream(self) -> None:
        for site_ref in (OTHER_SITE_REF, "g" * 24):
            status, value = self.request("GET", self._public_path(site_ref), token=TOKEN)
            self.assertNotEqual(status, 200)
            self.assertEqual(self.transport_calls, [])
            self.assertNotIn(SITE_ID, json.dumps(value))

    def test_controller_rejection_is_redacted_and_capability_unknown(self) -> None:
        self.fail_upstream = True
        status, value = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(value["error"], "openapi_rejected")
        cap = self.client.capabilities()
        operation = next(item for item in cap["items"]
                         if item["route"] == "GET /v1/sites/{site_ref}/wifi/channels")
        evidence = operation["runtime_evidence"][0]
        self.assertEqual(evidence["result"], "failure")
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertNotIn("private", json.dumps(value))

    def test_partial_projection_keeps_capability_unknown(self) -> None:
        partial_result = documented_result()
        del partial_result["5g channel stat"]
        self.result = partial_result
        status, value = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertTrue(value["partial"])
        self.assertIn("5g channel stat", value["missing_fields"])

        capability = self.client.capabilities()
        operation = next(item for item in capability["items"]
                         if item["route"] == "GET /v1/sites/{site_ref}/wifi/channels")
        evidence = operation["runtime_evidence"][0]
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["observation"], "response_partial")
        self.assertEqual(evidence["hardware_support_state"], "unknown")
        self.assertEqual(evidence["firmware_support_state"], "unknown")

    def test_only_fixed_get_path_controller_and_no_query_are_allowed(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        path = self._upstream_path()
        error = OpenApiError("connection_reached")
        with patch.object(client, "_connection", side_effect=error):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", path, token="token")
            rejected = (
                ("POST", path),
                ("PUT", path),
                ("PATCH", path),
                ("DELETE", path),
                ("GET", path + "?page=1"),
                ("GET", self._upstream_path("foreign-controller")),
                ("GET", path.replace("/dashboard/channels", "/dashboard/channel")),
            )
            for method, rejected_path in rejected:
                with self.subTest(method=method, path=rejected_path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, rejected_path, token="token")

    def test_public_route_rejects_other_methods_and_query_strings(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, _ = self.request(method, self._public_path(), token=TOKEN)
            self.assertNotEqual(status, 200)
        status, _ = self.request("GET", self._public_path() + "?debug=1", token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(self.transport_calls, [])


if __name__ == "__main__":
    unittest.main()
