from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_wan_port_availability_summary import (
    WanPortAvailabilityError, project_wan_port_availability)


class WanPortAvailabilitySummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_projects_documented_counts_and_discards_identifiers_addresses(self) -> None:
        projected = project_wan_port_availability({
            "enable": True,
            "wanPorts": [
                {"portName": "WAN/LAN1", "portUuid": "private-id", "type": 7,
                 "configured": True, "supportIptv": False, "virtualWanNum": 2,
                 "ipv6": True, "recommendedWan": True, "ip": "192.0.2.4"},
                {"portName": "WAN/LAN2", "portUuid": "private-id-2", "type": 7,
                 "configured": False, "supportIptv": True, "virtualWanNum": 0,
                 "ipv6": False, "recommendedWan": False, "ip": "192.0.2.5"},
            ]}, 7)
        self.assertEqual(projected["function"], 7)
        self.assertEqual(projected["listed_port_count"], 2)
        self.assertEqual(projected["qos_configured_count"], 1)
        self.assertEqual(projected["ipv6_enabled_count"], 1)
        self.assertEqual(projected["iptv_supported_count"], 1)
        self.assertEqual(projected["recommended_count"], 1)
        self.assertFalse(projected["partial"])
        self.assertNotIn("private-id", str(projected))
        self.assertNotIn("192.0.2.", str(projected))
        self.assertNotIn("WAN/LAN", str(projected))

    def test_missing_rows_are_unknown_not_zero_and_unknown_fields_mark_partial(self) -> None:
        missing = project_wan_port_availability({"enable": True}, 0)
        self.assertIsNone(missing["listed_port_count"])
        self.assertIsNone(missing["qos_configured_count"])
        self.assertTrue(missing["partial"])
        projected = project_wan_port_availability({
            "enable": True, "wanPorts": [{"configured": True, "vendorFuture": "secret"}]}, 0)
        self.assertTrue(projected["partial"])
        self.assertNotIn("secret", str(projected))

    def test_rejects_invalid_function_and_malformed_documented_fields(self) -> None:
        for function in (-1, 16, True):
            with self.assertRaises(WanPortAvailabilityError):
                project_wan_port_availability({"enable": True, "wanPorts": []}, function)
        with self.assertRaises(WanPortAvailabilityError):
            project_wan_port_availability({"enable": "yes", "wanPorts": []}, 0)
        with self.assertRaises(WanPortAvailabilityError):
            project_wan_port_availability({"enable": True, "wanPorts": [{"ipv6": 1}]}, 0)
        with self.assertRaises(WanPortAvailabilityError):
            project_wan_port_availability({"enable": True, "wanPorts": [{"type": "wan"}]}, 0)

    def test_adapter_uses_bound_site_and_exact_required_function_query(self) -> None:
        observed = []

        def request(method, path, **kwargs):
            observed.append((method, path))
            return {"result": {"enable": True, "wanPorts": []}}

        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_site_wan_port_availability_summary(self.site_ref, 15)
        self.assertEqual(observed, [("GET", "/openapi/v1/ctrl/sites/site_1/setting/wan-ports?function=15")])
        self.assertEqual(result["resource"], "site_wan_port_availability_summary")
        self.assertEqual(result["function"], 15)
        with self.assertRaisesRegex(OpenApiError, "wan_function_invalid"):
            self.client.read_site_wan_port_availability_summary(self.site_ref, 16)

    def test_upstream_allowlist_accepts_only_known_function_values_and_controller(self) -> None:
        path = "/openapi/v1/ctrl/sites/site_1/setting/wan-ports?function=15"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path)
        for invalid in (path.replace("function=15", "function=16"),
                        path.replace("/ctrl/", "/other/"), path + "&page=1"):
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", invalid)


if __name__ == "__main__":
    unittest.main()
