import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_wan_lan_status_summary import (
    SiteWanLanStatusSummaryError,
    project_site_wan_lan_status_summary,
)


def sample_result():
    return {
        "portName": {"port_1": "WAN 1", "port_2": "LAN 1"},
        "networkComptent": 3,
        "adoptedGateway": True,
        "supportIpv6": 1,
        "wanList": [{"portId": "private-port-id", "portName": "WAN 1",
                     "enable": 1, "networkId": "private-network-id", "proto": 1,
                     "pdEnable": 1, "prefix": "2001:db8::/64", "pdSize": 64}],
        "iptvPorts": ["private-iptv-port"],
        "preOsgModel": 1,
        "model": "private-model",
        "modelVersion": "private-version",
        "hasGateway": True,
    }


class SiteWanLanStatusSummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_projector_returns_only_flags_and_collection_counts(self):
        result = project_site_wan_lan_status_summary(sample_result())
        self.assertEqual(result["data"], {
            "gateway_adopted": True,
            "gateway_or_wan_override_present": True,
            "ipv6_support_code": 1,
            "network_component_present": True,
            "wan_port_count": 1,
            "iptv_port_count": 1,
            "named_port_count": 2,
        })
        self.assertFalse(result["partial"])
        for private in ("private-port-id", "private-network-id", "WAN 1",
                        "2001:db8::/64", "private-model", "private-version",
                        "private-iptv-port"):
            self.assertNotIn(private, repr(result))

    def test_projector_marks_invalid_and_unknown_values(self):
        payload = sample_result()
        payload["adoptedGateway"] = 1
        payload["wanList"][0]["extra"] = "private-extra"
        result = project_site_wan_lan_status_summary(payload)
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private-extra", repr(result))

    def test_projector_rejects_invalid_and_overbound_lists(self):
        with self.assertRaises(SiteWanLanStatusSummaryError):
            project_site_wan_lan_status_summary([])
        overbound = project_site_wan_lan_status_summary({"wanList": [{}] * 65})
        self.assertTrue(overbound["partial"])
        self.assertIsNone(overbound["data"]["wan_port_count"])

    def test_read_uses_fixed_site_path_without_query_inputs(self):
        def request(method, path, token):
            self.assertEqual(method, "GET")
            self.assertEqual(path, "/openapi/v1/ctrl/sites/site_1/wan-lan-status")
            self.assertTrue(self.client._site_wan_lan_status_request_valid(path))
            return {"result": sample_result()}
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request) as req:
            result = self.client.read_site_wan_lan_status_summary("e" * 24)
        req.assert_called_once()
        self.assertEqual(result["data"]["wan_port_count"], 1)

    def test_outbound_guard_pins_controller_and_fixed_route(self):
        good = "/openapi/v1/ctrl/sites/site/wan-lan-status"
        self.assertTrue(self.client._site_wan_lan_status_request_valid(good))
        for bad in (good.replace("/ctrl/", "/other/"), good + "?start=1",
                    good + "/extra"):
            self.assertFalse(self.client._site_wan_lan_status_request_valid(bad))

    def test_invalid_upstream_shape_fails_closed(self):
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaises(OpenApiError):
                self.client.read_site_wan_lan_status_summary("e" * 24)


if __name__ == "__main__":
    unittest.main()
