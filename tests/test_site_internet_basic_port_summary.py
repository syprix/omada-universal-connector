from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_internet_basic_port_summary import (
    SiteInternetBasicPortSummaryError, project_site_internet_basic_ports,
)


class SiteInternetBasicPortProjectionTests(unittest.TestCase):
    def test_counts_documented_port_codes_and_redacts_names_and_ids(self):
        result = project_site_internet_basic_ports({
            "preConfiguration": True, "gatewayModel": 42,
            "interval": 30,
            "portList": [
                {"portId": "private-id-1", "portName": "WAN private",
                 "portMode": 0, "portType": 1},
                {"portId": "private-id-2", "portName": "LAN private",
                 "portMode": 1, "portType": 0},
            ],
        })
        data = result["data"]
        self.assertTrue(data["preconfiguration_enabled"])
        self.assertTrue(data["gateway_model_reported"])
        self.assertEqual(data["online_detection_interval_seconds"], 30)
        self.assertEqual(data["port_mode_code_counts"], {"0": 1, "1": 1})
        self.assertEqual(data["port_type_code_counts"], {"0": 1, "1": 1})
        self.assertNotIn("private", repr(result))
        self.assertFalse(result["partial"])

    def test_missing_invalid_unknown_and_truncated_values_are_reported(self):
        result = project_site_internet_basic_ports({
            "gatewayModel": "private-model",
            "interval": -1,
            "portList": [{"portMode": 8, "portType": "unknown",
                          "unexpected": True}],
            "extra": "private",
        })
        self.assertTrue(result["partial"])
        self.assertGreater(result["missing_field_count"], 0)
        self.assertGreater(result["invalid_field_count"], 0)
        self.assertGreater(result["unknown_field_count"], 0)
        self.assertEqual(result["data"]["unknown_port_mode_code_count"], 1)
        self.assertTrue(project_site_internet_basic_ports({
            "preConfiguration": False, "gatewayModel": 1, "interval": 0,
            "portList": [{}] * 129,
        })["data"]["truncated"])
        with self.assertRaises(SiteInternetBasicPortSummaryError):
            project_site_internet_basic_ports([])


class SiteInternetBasicPortClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "internal_site"

    def test_reads_site_bound_basic_info_route(self):
        response = {"result": {"preConfiguration": True, "gatewayModel": 7,
                               "portList": [], "interval": 0}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=response) as request:
            result = self.client.read_site_internet_basic_port_summary(self.site_ref)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[1],
                         "/openapi/v1/ctrl/sites/internal_site/internet/basic-info")
        self.assertEqual(result["data"]["online_detection_interval_seconds"], 0)

    def test_path_guard_and_unknown_site(self):
        path = "/openapi/v1/ctrl/sites/internal_site/internet/basic-info"
        self.assertTrue(self.client._site_internet_basic_info_request_valid(path))
        self.assertFalse(self.client._site_internet_basic_info_request_valid(
            path.replace("/ctrl/", "/other/")))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_internet_basic_port_summary("b" * 24)


if __name__ == "__main__":
    unittest.main()
