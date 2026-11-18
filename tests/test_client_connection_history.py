from __future__ import annotations

import unittest
from datetime import datetime as RealDateTime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ClientConnectionHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.other_site_ref = "a" * 24, "c" * 24
        self.client._site_ids_by_ref = {self.site_ref: "site_1", self.other_site_ref: "site_2"}
        self.client._client_macs_by_site_ref = {
            self.site_ref: {"b" * 24: "00:11:22:33:44:55"},
            self.other_site_ref: {"d" * 24: "00:11:22:33:44:55"},
        }

    def test_fixed_24_hour_read_and_sanitized_timeline(self) -> None:
        now = 1_800_000_000_000
        payload = {"result": {
            "connections": [{"start": now - 1000, "end": now - 100,
                             "duration": 900, "ssid": "private", "apName": "secret",
                             "ip": "192.0.2.1", "mac": "00:11:22:33:44:55"}],
            "roamings": [{"start": now - 2000, "duration": 30,
                           "apName": "private", "message": "private"}],
        }}
        calls = []
        def request(method, path, **kwargs):
            calls.append((method, path))
            self.assertTrue(OmadaOpenApiClient._CLIENT_CONNECTION_REQUEST.fullmatch(path))
            return payload
        fixed_now = RealDateTime.fromtimestamp(now / 1000, timezone.utc)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = fixed_now
            result = self.client.read_client_connection_history(self.site_ref, "b" * 24)
        self.assertEqual(calls[0][0], "GET")
        self.assertIn("start=1799913600000", calls[0][1])
        self.assertIn("end=1800000000000", calls[0][1])
        self.assertEqual(result["window_end_ms"] - result["window_start_ms"], 86_400_000)
        self.assertEqual(result["items"], [
            {"kind": "roaming", "start_ms": now - 2000, "duration_ms": 30},
            {"kind": "connection", "start_ms": now - 1000, "duration_ms": 900,
             "end_ms": now - 100},
        ])
        for forbidden in ("00:11:22:33:44:55", "192.0.2.1", "private", "secret", "message"):
            self.assertNotIn(forbidden, str(result))
        evidence = next(x for x in self.client.capabilities()["items"]
                        if x["operation"] == "client_connection_history")["runtime_evidence"]
        self.assertEqual(evidence[0]["target_ref"], self.site_ref + ":" + "b" * 24)

    def test_reference_site_isolation_and_unknown_ref(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "client_ref_unknown"):
            self.client.read_client_connection_history(self.site_ref, "d" * 24)
        # A ref minted in another site's map does not authorize this site's lookup.
        with self.assertRaisesRegex(OpenApiError, "client_ref_unknown"):
            self.client.read_client_connection_history(self.site_ref, "d" * 24)

    def test_bad_history_schema_and_fixed_read_path(self) -> None:
        now = 1_800_000_000_000
        fixed_now = RealDateTime.fromtimestamp(now / 1000, timezone.utc)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "connections": [{"start": now + 1, "duration": 1}]}}), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = fixed_now
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_client_connection_history(self.site_ref, "b" * 24)
        allowed = "/openapi/v1/ctrl/sites/site_1/clients/00-11-22-33-44-55/client-connection?start=1&end=2"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("POST", allowed)

    def test_duration_accepts_raw_nonnegative_int64_without_inferred_end(self) -> None:
        now = 1_800_000_000_000
        fixed_now = RealDateTime.fromtimestamp(now / 1000, timezone.utc)
        payload = {"result": {"connections": [
            {"start": now - 1000, "duration": 2**63 - 1},
            {"start": now - 2000, "duration": 86_400_001},
        ]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = fixed_now
            result = self.client.read_client_connection_history(self.site_ref, "b" * 24)
        self.assertEqual(result["items"], [
            {"kind": "connection", "start_ms": now - 2000, "duration_ms": 86_400_001},
            {"kind": "connection", "start_ms": now - 1000, "duration_ms": 2**63 - 1},
        ])
        self.assertNotIn("end_ms", result["items"][0])
        self.assertNotIn("end_ms", result["items"][1])

    def test_duration_rejects_bool_negative_and_over_int64(self) -> None:
        now = 1_800_000_000_000
        fixed_now = RealDateTime.fromtimestamp(now / 1000, timezone.utc)
        for duration in (True, -1, 2**63):
            with self.subTest(duration=repr(duration)), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": {
                        "roamings": [{"start": now - 1, "duration": duration}]}}), \
                    patch("app.openapi.datetime") as dt:
                dt.now.return_value = fixed_now
                with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                    self.client.read_client_connection_history(self.site_ref, "b" * 24)


if __name__ == "__main__":
    unittest.main()
