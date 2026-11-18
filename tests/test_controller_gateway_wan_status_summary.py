from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from app.controller_gateway_wan_status_summary import (
    ControllerGatewayWanStatusSummaryError,
    project_controller_gateway_wan_status_summary,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


def payload() -> dict[str, object]:
    port = {"port": 0, "name": "private-wan", "type": 1, "physicalType": 1,
            "mode": 1, "status": 1, "internetState": 1, "ip": "192.0.2.8",
            "onlineDetection": 1, "ip2": "192.0.2.9", "speed": 1000, "duplex": 1,
            "rx": 100, "rxPkt": 10, "rxPktRate": 1, "rxRate": 20,
            "tx": 200, "txPkt": 20, "txPktRate": 2, "txRate": 30,
            "proto": "dhcp", "healthLevel": 6, "latency": 8,
            "loss": 0.5, "rxErrorPkts": 2, "txErrorPkts": 3}
    return {"totalRows": 5, "currentPage": 1, "currentSize": 2,
            "data": [{"siteId": "sensitive-site", "deviceMac": "sensitive-mac",
                      "uptime": "private", "wanStatus": [port]},
                     {"siteId": "other-site", "deviceMac": "other-mac",
                      "uptime": "private", "wanStatus": [port]}]}


class ControllerGatewayWanStatusSummaryTests(unittest.TestCase):
    def test_aggregates_diagnostics_and_omits_identity_fields(self) -> None:
        result = project_controller_gateway_wan_status_summary(payload(), requested_page_size=2)
        self.assertEqual(result["data"]["gateway_count"], 2)
        self.assertEqual(result["data"]["wan_port_count"], 2)
        self.assertEqual(result["data"]["has_more_pages"], True)
        self.assertEqual(result["data"]["physical_link_status_counts"], {"1": 2})
        self.assertEqual(result["data"]["average_latency_ms"], 8)
        self.assertEqual(result["data"]["average_packet_loss_percent"], 0.5)
        self.assertEqual(result["data"]["rx_rate_kilobytes_per_second_total"], 40)
        encoded = repr(result)
        for secret in ("sensitive-site", "sensitive-mac", "private-wan", "192.0.2.8"):
            self.assertNotIn(secret, encoded)
        self.assertFalse(result["partial"])

    def test_marks_missing_and_unknown_fields_partial_and_rejects_bounds(self) -> None:
        value = payload()
        value["data"][0]["wanStatus"][0]["futureField"] = True
        value["data"][0]["wanStatus"][0].pop("rxRate")
        result = project_controller_gateway_wan_status_summary(value, requested_page_size=2)
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertIsNone(result["data"]["rx_rate_kilobytes_per_second_total"])
        with self.assertRaises(ControllerGatewayWanStatusSummaryError):
            project_controller_gateway_wan_status_summary(payload(), requested_page_size=101)
        value = payload()
        value["data"] = [dict(value["data"][0]) for _ in range(3)]
        with self.assertRaises(ControllerGatewayWanStatusSummaryError):
            project_controller_gateway_wan_status_summary(value, requested_page_size=2)

    def test_client_pins_controller_and_validates_fixed_page_query(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        calls = []
        def upstream(method, path, **kwargs):
            calls.append((method, path))
            return {"result": payload()}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=upstream):
            summary = client.read_controller_gateway_wan_status_summary(0, 2)
        self.assertEqual(calls, [("GET", "/openapi/v1/ctrl/global/gateways/wan-status?page=1&pageSize=2")])
        self.assertEqual(summary["resource"], "controller_gateway_wan_status_summary")
        self.assertTrue(client._controller_gateway_wan_status_request_valid(
            "/openapi/v1/ctrl/global/gateways/wan-status?page=10001&pageSize=100"))
        for bad in (
            "/openapi/v1/other/global/gateways/wan-status?page=1&pageSize=2",
            "/openapi/v1/ctrl/global/gateways/wan-status?page=0&pageSize=2",
            "/openapi/v1/ctrl/global/gateways/wan-status?page=1&pageSize=101",
            "/openapi/v1/ctrl/global/gateways/wan-status?pageSize=2&page=1",
        ):
            self.assertFalse(client._controller_gateway_wan_status_request_valid(bad))
        for page, size in ((-1, 10), (0, 0), (0, 101), (True, 1)):
            with self.subTest(page=page, size=size), self.assertRaises(OpenApiError):
                client.read_controller_gateway_wan_status_summary(page, size)
