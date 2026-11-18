from __future__ import annotations

import builtins
import io
import json
import os
import re
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
AP_REF_1 = "b" * 24
AP_REF_2 = "c" * 24
AP_MAC = "AA-BB-CC-DD-EE-FF"
PRIVATE_NAME = "secret-room-ap"
PRIVATE_SITE_ID = "site_private"


class ApRetryDropIntegrationTests(unittest.TestCase):
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
        self.client._device_macs_by_site_ref[SITE_REF] = {AP_REF_1: AP_MAC}
        self.upstream: list[tuple[str, str, bytes | None]] = []
        self.result = {
            "retryEaps": [{"apMac": AP_MAC, "name": PRIVATE_NAME,
                           "model": "private-model", "retries": [
                               {"time": None, "retryTimes": 5, "retryRate": 0.25}]}],
            "droppedEaps": [],
        }

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.upstream.append((method, path, body))
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(token, "fixture-upstream-token")
            expected_prefix = ("/openapi/v1/ctrl/sites/site_private/"
                               "dashboard/retry-dropped-rate?")
            self.assertTrue(path.startswith(expected_prefix))
            query = parse_qs(urlsplit(path).query)
            start, end = int(query["start"][0]), int(query["end"][0])
            self.assertEqual(set(query), {"start", "end"})
            self.assertEqual(end - start, 86_400)
            retry_rows = self.result.get("retryEaps")
            if (isinstance(retry_rows, list) and retry_rows and
                    isinstance(retry_rows[0], dict) and
                    isinstance(retry_rows[0].get("retries"), list) and
                    retry_rows[0]["retries"] and isinstance(retry_rows[0]["retries"][0], dict)):
                retry_rows[0]["retries"][0]["time"] = end
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
    def _path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/aps/retry-drop"

    def request(self, method: str, path: str, *, token: str | None = None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {}
        connection.close()
        return response.status, result

    def test_authenticated_fixed_24h_seconds_and_redacted_projection(self) -> None:
        status, error = self.request("GET", self._path())
        self.assertEqual(status, 401)
        self.assertEqual(error["error"], "unauthorized")
        self.assertEqual(self.upstream, [])

        status, result = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(len(self.upstream), 1)
        method, path, body = self.upstream[0]
        self.assertEqual(method, "GET")
        self.assertIsNone(body)
        query = parse_qs(urlsplit(path).query)
        start, end = int(query["start"][0]), int(query["end"][0])
        self.assertEqual(end - start, 86_400)
        self.assertLess(abs(end - int(time.time())), 5)
        self.assertLess(end, 100_000_000_000)  # seconds, not milliseconds
        self.assertEqual(result["window_end_seconds"], end)
        self.assertEqual(result["window_start_seconds"], start)
        self.assertEqual(result["data"]["retry_aps"][0]["device_ref"], AP_REF_1)
        rendered = json.dumps(result)
        for private in (PRIVATE_SITE_ID, PRIVATE_NAME, AP_MAC, "private-model"):
            self.assertNotIn(private, rendered)
        self.assertNotIn("apMac", rendered)
        for private in (SITE_REF, PRIVATE_SITE_ID, PRIVATE_NAME, AP_MAC):
            self.assertNotIn(private, self.logs.getvalue())

    def test_unknown_site_and_missing_ap_inventory_do_not_call_upstream(self) -> None:
        before = len(self.upstream)
        status, error = self.request("GET", self._path("d" * 24), token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "site_ref_unknown")
        self.assertEqual(len(self.upstream), before)
        del self.client._device_macs_by_site_ref[SITE_REF]
        status, error = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "ap_inventory_unavailable")
        self.assertEqual(len(self.upstream), before)

    def test_duplicate_ap_mac_refs_are_preserved_and_projected_as_ambiguous(self) -> None:
        self.client._device_macs_by_site_ref[SITE_REF] = {
            AP_REF_1: AP_MAC, AP_REF_2: "aa:bb:cc:dd:ee:ff"}
        status, result = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 200)
        projected = result["data"]
        self.assertEqual(projected["retry_aps"], [])
        self.assertEqual(projected["omitted_ambiguous_ap_count"], 1)
        self.assertTrue(projected["partial"])
        self.assertNotIn(AP_REF_1, json.dumps(projected))
        self.assertNotIn(AP_REF_2, json.dumps(projected))

    def test_malformed_response_fields_fail_closed_without_leaking(self) -> None:
        self.result = {"retryEaps": None, "droppedEaps": []}
        status, error = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_response_invalid")
        self.result = {"retryEaps": [{"apMac": AP_MAC, "retries": [
            {"time": 1, "retryTimes": True, "retryRate": 0.2}]}],
            "droppedEaps": []}
        status, error = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_response_invalid")
        self.assertNotIn(AP_MAC, str(error))

    def test_only_get_route_is_exposed_and_capability_is_recorded(self) -> None:
        status, _ = self.request("POST", self._path(), token=self.token)
        self.assertEqual(status, 501)
        self.assertEqual(self.upstream, [])
        status, result = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 200)
        status, catalog = self.request("GET", "/v1/capabilities", token=self.token)
        self.assertEqual(status, 200)
        operation = next(item for item in catalog["items"]
                         if item["operation"] == "ap_retry_drop")
        self.assertEqual(operation["runtime_evidence"][0]["result"], "success")
        self.assertEqual(operation["runtime_evidence"][0]["target_ref"], SITE_REF)

    def test_upstream_allowlist_pins_controller_method_route_and_exact_24h(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id-file", "secret-file",
            cert_sha256="a" * 64))
        good = ("/openapi/v1/ctrl/sites/site_1/dashboard/retry-dropped-rate"
                "?start=1000000000&end=1000086400")
        with patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", good, token="token")
            for method, path in (
                ("GET", good.replace("/ctrl/", "/foreign/")),
                ("GET", good.replace("end=1000086400", "end=1000086399")),
                ("GET", good + "&extra=1"),
                ("GET", good.replace("?start=", "?end=").replace("&end=", "&start=")),
                ("POST", good),
            ):
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, token="token")


if __name__ == "__main__":
    unittest.main()
