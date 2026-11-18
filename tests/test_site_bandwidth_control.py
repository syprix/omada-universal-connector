from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_bandwidth_control import (
    SiteBandwidthControlError,
    project_site_bandwidth_control,
)


class SiteBandwidthControlProjectionTests(unittest.TestCase):
    def test_summarizes_ports_and_never_returns_port_ids(self) -> None:
        result = project_site_bandwidth_control({
            "enable": True, "thresholdControlEnable": True, "thresholdValue": 50,
            "bandwidthPortSettings": [
                {"portUuid": "private-port-1", "upstreamBandwidth": 1000,
                 "upstreamBandwidthUnit": 1, "downstreamBandwidth": 2,
                 "downstreamBandwidthUnit": 2},
                {"portUuid": "private-port-2", "upstreamBandwidth": 3,
                 "upstreamBandwidthUnit": 2},
            ],
        })
        self.assertEqual(result["data"]["returned_port_count"], 2)
        self.assertEqual(result["data"]["valid_port_count"], 2)
        self.assertEqual(result["data"]["upstream_bandwidth_totals"],
                         {"kbps": 1000, "mbps": 3})
        self.assertEqual(result["data"]["downstream_bandwidth_totals"],
                         {"kbps": 0, "mbps": 2})
        self.assertFalse(result["partial"])
        self.assertNotIn("private-port", repr(result))

    def test_threshold_value_is_required_only_when_control_is_enabled(self) -> None:
        required = project_site_bandwidth_control({
            "enable": True, "thresholdControlEnable": True,
        })
        optional = project_site_bandwidth_control({
            "enable": True, "thresholdControlEnable": False,
        })
        self.assertEqual(required["missing_field_count"], 1)
        self.assertTrue(required["partial"])
        self.assertEqual(optional["missing_field_count"], 0)
        self.assertFalse(optional["partial"])

    def test_invalid_ports_and_unknown_fields_are_counted(self) -> None:
        result = project_site_bandwidth_control({
            "enable": True, "bandwidthPortSettings": [
                {"portUuid": "id", "upstreamBandwidth": 0,
                 "upstreamBandwidthUnit": 1},
                {"portUuid": "other", "private": "not returned"},
            ],
            "extra": "not returned",
        })
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertEqual(result["data"]["valid_port_count"], 1)
        self.assertNotIn("not returned", repr(result))

    def test_rejects_invalid_outer_shapes(self) -> None:
        for value in (None, [], {str(i): i for i in range(17)}):
            with self.subTest(shape=type(value).__name__), self.assertRaises(
                    SiteBandwidthControlError):
                project_site_bandwidth_control(value)


class SiteBandwidthControlClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_path(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "enable": True, "thresholdControlEnable": False}}) as request:
            result = self.client.read_site_bandwidth_control(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/bandwidth-control",
            token="test-token")
        self.assertEqual(result["data"]["enabled"], True)

    def test_rejects_invalid_response_and_unknown_site(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_bandwidth_control(self.site_ref)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_bandwidth_control("7" * 24)

    def test_path_guard_binds_controller(self) -> None:
        self.assertTrue(self.client._site_bandwidth_control_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/bandwidth-control"))
        self.assertFalse(self.client._site_bandwidth_control_request_valid(
            "/openapi/v1/other/sites/site_internal/bandwidth-control"))


if __name__ == "__main__":
    unittest.main()
