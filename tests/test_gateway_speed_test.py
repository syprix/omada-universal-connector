from __future__ import annotations

import unittest
from unittest.mock import patch

from app.gateway_speed_test import GatewaySpeedTestError, project_gateway_speed_test
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF, GATEWAY_REF = "a" * 24, "d" * 24
GATEWAY_MAC = "00:11:22:33:44:77"


class GatewaySpeedTestProjectionTests(unittest.TestCase):
    def test_projects_saved_numeric_results_and_redacts_labels(self) -> None:
        result = project_gateway_speed_test({"status": 1, "portSpeedResults": [{
            "portId": 2, "virtualWanEntryId": 7, "time": 1730000000,
            "portName": "private port", "isp": "Example ISP", "serverName": "server",
            "serverLocation": "private location", "status": 0, "latency": 12,
            "down": 900000, "up": 400000, "progress": 100.0,
        }]})
        self.assertFalse(result["data"]["partial"])
        self.assertEqual(result["data"]["items"], [{
            "portId": 2, "virtualWanEntryId": 7, "time": 1730000000,
            "status": 0, "latency": 12, "down": 900000, "up": 400000,
            "progress": 100.0,
        }])
        self.assertEqual(result["data"]["redacted_field_count"], 4)
        self.assertNotIn("Example ISP", repr(result))

    def test_invalid_values_unknown_fields_and_bounds(self) -> None:
        result = project_gateway_speed_test({"status": 0, "portSpeedResults": [{
            "portId": True, "down": -1, "progress": float("inf"), "private": "x",
        }]})
        self.assertTrue(result["data"]["partial"])
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertEqual(result["data"]["items"], [])
        for raw in (None, {}, {"status": 0, "portSpeedResults": None},
                    {"status": 0, "portSpeedResults": [{}] * 65}):
            with self.subTest(raw=raw), self.assertRaises(GatewaySpeedTestError):
                project_gateway_speed_test(raw)


class GatewaySpeedTestClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._gateway_macs_by_site_ref[SITE_REF] = {GATEWAY_REF: GATEWAY_MAC}

    def test_reads_only_the_fixed_saved_results_route(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"status": 0, "portSpeedResults": []}}) as request:
            result = self.client.read_gateway_speed_test_results(SITE_REF, GATEWAY_REF)
        request.assert_called_once_with(
            "GET", f"/openapi/v1/ctrl/sites/site_1/gateways/{GATEWAY_MAC}/speedTestResult",
            token="token")
        self.assertEqual(result["resource"], "gateway_speed_test_results")

    def test_saved_results_route_passes_the_fixed_upstream_read_guard(self) -> None:
        path = f"/openapi/v1/ctrl/sites/site_1/gateways/{GATEWAY_MAC}/speedTestResult"
        with patch.object(self.client, "_connection",
                          side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path)

    def test_unlisted_gateway_result_paths_remain_rejected(self) -> None:
        path = f"/openapi/v1/ctrl/sites/site_1/gateways/{GATEWAY_MAC}/speedTestResult/private"
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", path)

    def test_unknown_gateway_is_rejected_before_request(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "gateway_ref_unknown"):
                self.client.read_gateway_speed_test_results(SITE_REF, "e" * 24)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
