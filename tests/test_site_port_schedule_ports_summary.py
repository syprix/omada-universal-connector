from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_port_schedule_ports_summary import (
    PortSchedulePortsError, summarize_port_schedule_ports,
)


class PortSchedulePortsSummaryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_counts_schedule_capable_ports_and_redacts_device_values(self):
        result = summarize_port_schedule_ports([
            {"type": "gateway", "mac": "private", "name": "private",
             "status": 7, "ports": {"portNum": 5, "portIds": [1, 2]}},
            {"type": "switch", "mac": "private2",
             "ports": {"portNum": 8, "portIds": [3, 4, 5]}},
        ])
        self.assertEqual(result["reported_device_count"], 2)
        self.assertEqual(result["device_type_counts"],
                         {"gateway": 1, "switch": 1, "unknown": 0})
        self.assertEqual(result["device_port_count"], 13)
        self.assertEqual(result["schedule_capable_port_count"], 5)
        self.assertEqual(result["reported_device_status_field_count"], 1)
        for secret in ("private", "portIds", "mac"):
            self.assertNotIn(secret, repr(result))
        self.assertFalse(result["partial"])

    def test_marks_unknown_types_fields_bad_values_and_truncation(self):
        result = summarize_port_schedule_ports([
            {"type": "ap", "future": "private",
             "ports": {"portNum": 2, "portIds": [True, 1]}},
            None, {},
        ], max_items=2)
        self.assertTrue(result["partial"])
        self.assertEqual(result["device_type_counts"]["unknown"], 2)
        self.assertEqual(result["invalid_record_count"], 1)
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["truncated"])
        with self.assertRaises(PortSchedulePortsError):
            summarize_port_schedule_ports({"result": []})

    def test_reads_fixed_site_bound_path(self):
        payload = {"result": [{"type": "switch", "status": 0,
                               "ports": {"portNum": 4, "portIds": [1, 2]}}]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_site_port_schedule_ports_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/port-status-ports",
            token="token")
        self.assertEqual(result["schedule_capable_port_count"], 2)
        self.assertTrue(self.client._site_port_schedule_ports_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/port-status-ports"))
        self.assertFalse(self.client._site_port_schedule_ports_request_valid(
            "/openapi/v1/other/sites/site_internal/port-status-ports"))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_port_schedule_ports_summary("7" * 24)


if __name__ == "__main__":
    unittest.main()
