from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_wan_ports_summary import SiteWanPortsError, project_site_wan_ports


def sample() -> dict[str, object]:
    return {
        "wanPortsConfig": [{
            "portId": "private-port-id", "portName": "WAN",
            "wanPortIpv4Setting": {"protoType": 2, "vlanId": 10, "qosTagEnable": False,
                                   "ipv4Pppoe": {"userName": "private-user", "password": "private-secret"}},
            "wanPortIpv6Setting": {"enable": True, "protoType": 1},
            "wanPortMacSetting": {"method": 0, "mac": "private-mac"},
            "dslSetting": {"portUuid": "private-dsl-id", "isp": 1, "location": "x",
                           "modulationType": 2, "merEnable": True, "merPassword": "hidden"},
        }],
        "UsbPortsConfig": [{"portId": "private-usb-id", "authType": 0, "configType": 1,
                            "connectionMode": 2, "dnsEnable": True, "mtuSize": 1500,
                            "pin": "hidden", "manuallyConfig": {"password": "hidden"}}],
    }


class SiteWanPortsProjectionTests(unittest.TestCase):
    def test_returns_bounded_counts_and_codes_without_sensitive_values(self) -> None:
        projected = project_site_wan_ports(sample())
        self.assertEqual(projected["data"]["wan_port_count"], 1)
        self.assertEqual(projected["data"]["valid_wan_port_count"], 1)
        self.assertEqual(projected["data"]["ipv4_protocol_code_counts"], {"2": 1})
        self.assertEqual(projected["data"]["ipv6_enabled_port_count"], 1)
        self.assertEqual(projected["data"]["usb_lte_port_count"], 1)
        self.assertEqual(projected["data"]["usb_config_type_code_counts"], {"1": 1})
        self.assertFalse(projected["partial"])
        for secret in ("private-port-id", "private-user", "private-secret", "private-mac",
                       "private-dsl-id", "hidden", "private-usb-id"):
            self.assertNotIn(secret, repr(projected))

    def test_missing_arrays_and_required_fields_are_partial(self) -> None:
        projected = project_site_wan_ports({"wanPortsConfig": [], "UsbPortsConfig": []})
        self.assertFalse(projected["partial"])
        projected = project_site_wan_ports({"wanPortsConfig": [{}], "UsbPortsConfig": []})
        self.assertTrue(projected["partial"])
        self.assertGreater(projected["missing_field_count"], 0)

    def test_invalid_shape_range_and_unknown_fields_are_counted(self) -> None:
        source = sample()
        source["UsbPortsConfig"][0]["mtuSize"] = 1501
        source["private"] = "never returned"
        projected = project_site_wan_ports(source)
        self.assertGreater(projected["invalid_field_count"], 0)
        self.assertEqual(projected["unknown_field_count"], 1)
        self.assertNotIn("never returned", repr(projected))

    def test_rejects_invalid_outer_shapes(self) -> None:
        for value in (None, [], {str(i): i for i in range(17)}):
            with self.subTest(shape=type(value).__name__), self.assertRaises(SiteWanPortsError):
                project_site_wan_ports(value)


class SiteWanPortsClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_path_and_projects_response(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": sample()}) as request:
            result = self.client.read_site_wan_ports_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/internet/ports-config", token="test-token")
        self.assertEqual(result["data"]["wan_port_count"], 1)
        self.assertNotIn("private-secret", repr(result))

    def test_rejects_invalid_response_and_unknown_site(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_wan_ports_summary(self.site_ref)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_wan_ports_summary("7" * 24)

    def test_path_guard_binds_controller(self) -> None:
        self.assertTrue(self.client._site_wan_ports_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/internet/ports-config"))
        self.assertFalse(self.client._site_wan_ports_request_valid(
            "/openapi/v1/other/sites/site_internal/internet/ports-config"))


if __name__ == "__main__":
    unittest.main()
