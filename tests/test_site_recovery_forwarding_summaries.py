from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_intelli_recover_summary import summarize_intelli_recover_settings
from app.site_port_forwarding_summary import summarize_port_forwarding_rows


class SiteRecoveryForwardingSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.config = OpenApiConfig(
            "https://controller.example", "controller_1", "client", "secret",
            cert_sha256="a" * 64, page_size=2, max_pages=3,
        )
        self.client = OmadaOpenApiClient(self.config)
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-1"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_recovery_summary_omits_interval_values_and_setting_id(self) -> None:
        result = summarize_intelli_recover_settings({
            "id": "private-setting-id", "autoFlag": True, "limitNum": 4,
            "firstRebootPoeInterval": 60, "rebootPoeInterval": 90,
        })
        self.assertTrue(result["automatic_recovery_enabled"])
        self.assertEqual(result["reboot_device_limit"], 4)
        self.assertTrue(result["initial_interval_reported"])
        self.assertTrue(result["retry_interval_reported"])
        self.assertFalse(result["interval_units_documented"])
        self.assertNotIn("60", json.dumps(result))
        self.assertNotIn("90", json.dumps(result))
        self.assertNotIn("private-setting-id", json.dumps(result))

    def test_recovery_summary_marks_missing_unitless_settings_partial(self) -> None:
        result = summarize_intelli_recover_settings({"autoFlag": False})
        self.assertFalse(result["automatic_recovery_enabled"])
        self.assertIsNone(result["reboot_device_limit"])
        self.assertFalse(result["initial_interval_reported"])
        self.assertTrue(result["partial"])

    def test_recovery_client_reads_fixed_site_path_and_redacts_result(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"id": "private", "autoFlag": True, "limitNum": 3,
                               "firstRebootPoeInterval": 10, "rebootPoeInterval": 20},
                }) as request:
            result = self.client.read_site_intelli_recover_summary(self.site_ref)
        self.assertEqual(request.call_args.args[1],
                         "/openapi/v1/controller_1/sites/site-1/intelli-recover/auto-setting/config")
        self.assertEqual(result["reboot_device_limit"], 3)
        self.assertNotIn("private", json.dumps(result))
        self.assertNotIn("10", json.dumps(result))

    def test_port_forwarding_projection_counts_only_status_protocol_and_source(self) -> None:
        rows = [
            {"id": "private", "name": "private", "status": True, "from": 0,
             "protocol": 0, "externalPort": "443", "forwardIp": "192.0.2.4",
             "interfaceWanPortId": ["wan-private"]},
            {"status": False, "from": 1, "protocol": 1,
             "limitedAddresses": ["198.51.100.5"]},
            {"status": True, "from": 1, "protocol": 2, "virtualWanId": ["private"]},
            {"status": None, "from": 8, "protocol": 7},
        ]
        result = summarize_port_forwarding_rows(rows, 5, 1)
        self.assertEqual(result["status_counts"],
                         {"enabled": 2, "disabled": 1, "unknown": 1})
        self.assertEqual(result["protocol_counts"],
                         {"all": 1, "tcp": 1, "udp": 1, "unknown": 1})
        self.assertEqual(result["source_counts"],
                         {"code_0": 1, "limited_address": 2, "unknown": 1})
        self.assertEqual(result["omitted_rule_count"], 1)
        self.assertTrue(result["partial"])
        for secret in ("private", "443", "192.0.2.4", "198.51.100.5"):
            self.assertNotIn(secret, json.dumps(result))

    def test_port_forwarding_reader_keeps_page_size_and_caps_rows(self) -> None:
        pages = [
            {"errorCode": 0, "result": {"totalRows": 9, "currentPage": 1,
             "currentSize": 2, "data": [{"status": True, "from": 0, "protocol": 0},
                                          {"status": False, "from": 1, "protocol": 1}]}},
            {"errorCode": 0, "result": {"totalRows": 9, "currentPage": 2,
             "currentSize": 2, "data": [{"status": True, "from": 1, "protocol": 2},
                                          {"status": True, "from": 0, "protocol": 0}]}},
            {"errorCode": 0, "result": {"totalRows": 9, "currentPage": 3,
             "currentSize": 2, "data": [{"status": False, "from": 0, "protocol": 1},
                                          {"status": True, "from": 1, "protocol": 2}]}},
        ]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=pages) as request:
            result = self.client.read_site_port_forwarding_summary(self.site_ref)
        self.assertEqual(result["rule_count"], 6)
        self.assertEqual(result["reported_total_count"], 9)
        self.assertEqual(result["omitted_rule_count"], 3)
        self.assertFalse(result["coverage_complete"])
        paths = [call.args[1] for call in request.call_args_list]
        self.assertEqual(paths, [
            "/openapi/v1/controller_1/sites/site-1/nat/port-forwardings?page=1&pageSize=2",
            "/openapi/v1/controller_1/sites/site-1/nat/port-forwardings?page=2&pageSize=2",
            "/openapi/v1/controller_1/sites/site-1/nat/port-forwardings?page=3&pageSize=2",
        ])

    def test_port_forwarding_rejects_inconsistent_empty_grid_placeholder(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"totalRows": 0, "currentPage": 0, "currentSize": 0,
                               "data": [{"status": True}]},
                }):
            with self.assertRaises(OpenApiError) as caught:
                self.client.read_site_port_forwarding_summary(self.site_ref)
        self.assertEqual(caught.exception.code, "openapi_response_invalid")

    def test_site_read_path_guards_are_exact_and_bounded(self) -> None:
        recovery = "/openapi/v1/controller_1/sites/site-1/intelli-recover/auto-setting/config"
        forwarding = "/openapi/v1/controller_1/sites/site-1/nat/port-forwardings?page=3&pageSize=1000"
        self.assertTrue(self.client._site_intelli_recover_settings_request_valid(recovery))
        self.assertTrue(self.client._site_port_forwardings_request_valid(forwarding))
        self.assertFalse(self.client._site_intelli_recover_settings_request_valid(
            recovery + "?mode=write"))
        self.assertFalse(self.client._site_port_forwardings_request_valid(
            forwarding + "&name=private"))


if __name__ == "__main__":
    unittest.main()
