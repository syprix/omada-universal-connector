from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class FixedDateTime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 1, 2, 12, 0, tzinfo=tz or timezone.utc)


class ApHealthIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.ap_ref = "a" * 24, "b" * 24
        self.mac = "AA-BB-CC-DD-EE-FF"
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._device_macs_by_site_ref[self.site_ref] = {self.ap_ref: self.mac}

    def test_health_uses_inventory_ref_fixed_24h_and_redacted_projector(self) -> None:
        end_ms = int(FixedDateTime.now(timezone.utc).timestamp() * 1000)
        start_ms = end_ms - 86_400_000
        private = "00:11:22:33:44:55"
        payload = {"result": {"score": 92,
            "cpu": {"summaryScore": 89, "support": True, "averageNum": 17,
                    "pastNums": [{"time": end_ms, "pastNum": 16}],
                    "incidents": [{"incidentId": "private-incident", "macs": [private],
                                   "titleParams": {"person": "private-name"}}]},
            "incident": {"incidentNum": 1, "incidents": [{"ip": "192.0.2.4"}]},
            "name": "private AP", "ip": "192.0.2.5"}}
        with patch("app.openapi.datetime", FixedDateTime), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_ap_health(self.site_ref, self.ap_ref)
        request.assert_called_once_with("GET",
            f"/openapi/v1/ctrl/sites/site_1/eaps/{self.mac}/health/detail?start={start_ms}&end={end_ms}",
            token="token")
        self.assertEqual(result["window_start_ms"], start_ms)
        self.assertEqual(result["window_end_ms"], end_ms)
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["score"], 92)
        self.assertEqual(result["data"]["cpu"]["average"], 17)
        self.assertEqual(result["data"]["cpu"]["incidents_count"], 1)
        for private_value in (self.mac, private, "private-incident", "private-name", "private AP",
                              "192.0.2.4", "192.0.2.5"):
            self.assertNotIn(private_value, str(result))
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "ap_health")["runtime_evidence"]
        self.assertEqual(evidence[0]["target_ref"], self.site_ref + ":" + self.ap_ref)

    def test_health_partial_tracks_only_explicit_projection_gap_markers(self) -> None:
        end_ms = int(FixedDateTime.now(timezone.utc).timestamp() * 1000)
        start_ms = end_ms - 86_400_000
        cases = (
            ({"cpu": {"pastNums": [{"time": end_ms, "pastNum": None}]}}, True,
             "missing_value_points"),
            ({"cpu": {"pastNums": [{"time": end_ms + 1, "pastNum": 5}]}}, True,
             "discarded_out_of_window_points"),
            ({"cpu": {"averageNum": -1}}, True, "unclassified_minus_one_fields"),
            ({"cpu": {"pastNums": [{"time": end_ms, "pastNum": 5}]}}, False, None),
        )
        for raw, expected_partial, marker in cases:
            with self.subTest(marker=marker), \
                    patch("app.openapi.datetime", FixedDateTime), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": raw}):
                result = self.client.read_ap_health(self.site_ref, self.ap_ref)
            self.assertIs(result["partial"], expected_partial)
            if marker == "unclassified_minus_one_fields":
                self.assertTrue(result["data"][marker])
            elif marker:
                self.assertEqual(result["data"]["cpu"][marker], 1)

    def test_unknown_site_bound_ap_ref_fails_before_upstream_call(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
                self.client.read_ap_health(self.site_ref, "c" * 24)
        request.assert_not_called()

    def test_fixed_path_allowlist_enforces_exact_24_hour_window(self) -> None:
        end_ms = 1_800_000_000_000
        start_ms = end_ms - 86_400_000
        good = f"/openapi/v1/ctrl/sites/site_1/eaps/{self.mac}/health/detail?start={start_ms}&end={end_ms}"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
            for path in (good.replace(f"start={start_ms}", f"start={start_ms - 1}"),
                         good + "&include=raw", good.replace("/eaps/", "/aps/")):
                with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                    self.client._request_json("GET", path)
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("PATCH", good)

    def test_http_route_dispatches_and_rejects_missing_caller_auth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token = "caller-token-0123456789abcdef0123456789"
            token_file = os.path.join(directory, "token")
            with open(token_file, "w", encoding="utf-8") as handle:
                handle.write(token)

            class FakeClient:
                def __init__(self): self.calls = []
                def read_ap_health(self, site_ref, ap_ref):
                    self.calls.append((site_ref, ap_ref))
                    return {"status": "ok", "resource": "ap_health", "data": {"score": 90}}

            fake = FakeClient()
            with patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": token_file}), \
                    patch.object(main, "_openapi_client", return_value=fake):
                server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    path = f"/v1/sites/{self.site_ref}/aps/{self.ap_ref}/health"
                    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    conn.request("GET", path)
                    denied = conn.getresponse()
                    self.assertEqual(denied.status, 401)
                    denied.read(); conn.close()
                    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    conn.request("GET", path, headers={"Authorization": "Bearer " + token})
                    response = conn.getresponse()
                    body = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    self.assertEqual(body["resource"], "ap_health")
                    conn.close()
                    self.assertEqual(fake.calls, [(self.site_ref, self.ap_ref)])
                finally:
                    server.shutdown(); thread.join(timeout=2); server.server_close()


if __name__ == "__main__":
    unittest.main()
