from __future__ import annotations

import unittest
from unittest.mock import patch

from app.gateway_internet import GatewayInternetError, project_gateway_internet
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF, GATEWAY_REF = "a" * 24, "d" * 24
GATEWAY_MAC = "00:11:22:33:44:77"


class GatewayInternetProjectionTests(unittest.TestCase):
    def test_projects_capabilities_and_anonymous_online_code_counts(self) -> None:
        result = project_gateway_internet({
            "enable": True, "supportCustomInterval": True, "supportLte": False,
            "interval": 10, "unit": 1, "supportMaxWanNum": 4, "supportDualSim": 1,
            "gatewayMac": GATEWAY_MAC, "siteId": "private-site",
            "wanPortSettings": [{"ip": "192.0.2.1"}],
            "portOnlineStatus": {"wanOnlineStatus": [
                {"portUuid": "private-port", "onlineDetection": 1},
                {"portUuid": "private-port-2", "onlineDetection": 0}],
                "virtualWanOnlineStatus": [{"virtualWanId": "private-vwan",
                                            "onlineDetection": 1}]},
        })
        self.assertFalse(result["data"]["partial"])
        self.assertTrue(result["data"]["support"]["custom_interval"])
        self.assertFalse(result["data"]["support"]["lte"])
        self.assertEqual(result["data"]["settings"], {
            "internet_enabled": True, "interval_code": 10, "unit_code": 1,
            "max_wan_count": 4, "dual_sim_support_code": 1,
        })
        self.assertEqual(result["data"]["online_detection_code_counts"], {
            "wan": [{"code": 0, "count": 1}, {"code": 1, "count": 1}],
            "virtual_wan": [{"code": 1, "count": 1}],
        })
        self.assertEqual(result["data"]["redacted_field_count"], 6)
        for private in (GATEWAY_MAC, "private-site", "private-port", "private-vwan", "192.0.2.1"):
            self.assertNotIn(private, repr(result))

    def test_invalid_unknown_and_unbounded_data_mark_partial_or_fail(self) -> None:
        result = project_gateway_internet({
            "enable": 1, "supportLte": "yes", "privateField": "hidden",
            "portOnlineStatus": {"wanOnlineStatus": [{"onlineDetection": "up"}],
                                 "privateGroup": []},
        })
        self.assertTrue(result["data"]["partial"])
        self.assertEqual(result["data"]["unknown_field_count"], 2)
        for raw in (None, [], {"enable": True} | {f"x{i}": 0 for i in range(65)}):
            with self.subTest(raw=raw), self.assertRaises(GatewayInternetError):
                project_gateway_internet(raw)
        oversized_statuses = project_gateway_internet({
            "portOnlineStatus": {"wanOnlineStatus": [None] * 65}})
        self.assertTrue(oversized_statuses["data"]["partial"])


class GatewayInternetClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._gateway_macs_by_site_ref[SITE_REF] = {GATEWAY_REF: GATEWAY_MAC}

    def test_reads_fixed_gateway_internet_route(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"enable": True, "supportLte": False}}) as request:
            result = self.client.read_gateway_internet_info(SITE_REF, GATEWAY_REF)
        request.assert_called_once_with(
            "GET", f"/openapi/v1/ctrl/sites/site_1/gateways/{GATEWAY_MAC}/internet",
            token="token")
        self.assertEqual(result["resource"], "gateway_internet_info")
        self.assertEqual(result["device_ref"], GATEWAY_REF)

    def test_unknown_gateway_is_rejected_before_request(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "gateway_ref_unknown"):
                self.client.read_gateway_internet_info(SITE_REF, "e" * 24)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
