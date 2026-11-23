from __future__ import annotations

import unittest
from datetime import datetime as RealDateTime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ClientHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.client_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._client_macs_by_site_ref[self.site_ref] = {
            self.client_ref: "00:11:22:33:44:55"}

    def test_24h_health_query_and_numeric_allowlist(self) -> None:
        now = 1_800_000_000_000
        point = now - 5_000
        payload = {"result": {
            "score": 88,
            "associationTime": {"summaryScore": 75, "averageNum": [{"time": point, "pastNum": 1200}]},
            "rssi": {"summaryScore": 91, "averageNum": [{"time": point, "pastNum": -56}]},
            "rate": {"summaryScore": 82, "averageNum": [{"time": point, "pastNum": 866000}]},
            "snr": {"summaryScore": 89, "averageNum": [{"time": point, "pastNum": 31}]},
            "connectScore": {"summaryScore": 90, "averageNum": []},
            "linkErrorScore": {"summaryScore": 99},
            "incident": {"summaryScore": 84, "support": True, "incidentNum": 2,
                         "incidents": [{"incidentId": "secret-id", "titleParams": {"name": "private"},
                                        "macs": ["00:11:22:33:44:55"], "lastTime": point}]},
            "name": "private", "ip": "192.0.2.1", "ssid": "private", "rssiText": "private"}}
        paths = []
        def request(method, path, **kwargs):
            paths.append(path)
            self.assertEqual(method, "GET")
            self.assertTrue(OmadaOpenApiClient._CLIENT_HEALTH_REQUEST.fullmatch(path))
            return payload
        fixed_now = RealDateTime.fromtimestamp(now / 1000, timezone.utc)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = fixed_now
            result = self.client.read_client_health(self.site_ref, self.client_ref)
        self.assertIn("start=1799913600000", paths[0])
        self.assertIn("end=1800000000000", paths[0])
        self.assertEqual(result["window_end_ms"] - result["window_start_ms"], 86_400_000)
        self.assertEqual(result["data"]["score"], 88)
        self.assertEqual(result["data"]["rssi"]["values"][0]["value"], -56)
        self.assertEqual(result["data"]["rate"]["values"][0]["value"], 866000)
        self.assertEqual(result["data"]["incident"], {"summary_score": 84,
                         "supported": True, "incident_count": 2})
        for forbidden in ("secret-id", "private", "192.0.2.1", "00:11:22:33:44:55", "ssid", "incidents"):
            self.assertNotIn(forbidden, str(result))
        cap = next(item for item in self.client.capabilities()["items"]
                   if item["operation"] == "client_health")
        self.assertEqual(cap["runtime_evidence"][0]["target_ref"],
                         self.site_ref + ":" + self.client_ref)

    def test_unknown_reference_and_out_of_range_values_fail(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "client_ref_unknown"):
            self.client.read_client_health(self.site_ref, "c" * 24)
        now = 1_800_000_000_000
        fixed_now = RealDateTime.fromtimestamp(now / 1000, timezone.utc)
        for result in ({"score": 101}, {"score": -2},
                       {"rssi": {"averageNum": [{"time": now, "pastNum": -200}]}},
                       {"snr": {"averageNum": [{"time": now + 1, "pastNum": 20}]}}):
            with patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": result}), \
                    patch("app.openapi.datetime") as dt:
                dt.now.return_value = fixed_now
                with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                    self.client.read_client_health(self.site_ref, self.client_ref)

    def test_live_minus_one_score_sentinels_are_reported_as_unclassified(self) -> None:
        now = 1_800_000_000_000
        fixed_now = RealDateTime.fromtimestamp(now / 1000, timezone.utc)
        payload = {"result": {
            "score": -1,
            "associationTime": {"summaryScore": -1, "averageNum": None},
            "rssi": {"summaryScore": -1},
            "rate": {"summaryScore": -1},
            "snr": {"summaryScore": -1},
            "connectScore": {"summaryScore": None},
            "linkErrorScore": {"summaryScore": None},
            "incident": {"summaryScore": -1, "incidentNum": 0},
        }}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = fixed_now
            result = self.client.read_client_health(self.site_ref, self.client_ref)

        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["score"], None)
        self.assertEqual(result["data"]["association_time_ms"]["summary_score"], None)
        self.assertEqual(result["data"]["rssi"]["summary_score"], None)
        self.assertEqual(result["data"]["incident"]["summary_score"], None)
        self.assertEqual(result["unclassified_minus_one_fields"], [
            "score", "associationTime.summaryScore", "rssi.summaryScore",
            "rate.summaryScore", "snr.summaryScore", "incident.summaryScore",
        ])
        self.assertNotIn(-1, result["data"].values())

    def test_fixed_read_path_only(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/clients/00-11-22-33-44-55/health/detail?start=1&end=2"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", allowed + "&verbose=true")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("POST", allowed)


if __name__ == "__main__":
    unittest.main()
