from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE = "a" * 24
AP = "b" * 24


class CapabilityCompletenessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE] = "site-id"
        self.client._device_macs_by_site_ref[SITE] = {AP: "00:11:22:33:44:55"}
        self.payload = {"errorCode": 0, "result": {}}
        self.request = patch.object(self.client, "_request_json", side_effect=self._request)
        self.request.start()
        self.token = patch.object(self.client, "_access_token", return_value="fake-token")
        self.token.start()

    def tearDown(self) -> None:
        self.token.stop()
        self.request.stop()

    def _request(self, method: str, path: str, **_kwargs):
        self.assertEqual(method, "GET")
        self.assertNotIn("controller.example", path)
        return self.payload

    def evidence(self, operation: str) -> dict[str, object]:
        item = next(row for row in self.client.capabilities()["items"]
                    if row["operation"] == operation)
        return item["runtime_evidence"][-1]

    def test_fixture_payload_shape_is_not_reported_as_live_controller_support(self):
        self.payload = {"result": {"totalApNum": 2}}
        self.client.read_site_overview(SITE)
        fixture_evidence = self.evidence("site_overview")
        self.assertEqual(fixture_evidence["response_shape_state"],
                         "response_shape_supported")
        self.assertEqual(fixture_evidence["support_state"], "unknown")
        self.assertEqual(fixture_evidence["permission_state"], "unknown")
        self.assertFalse(fixture_evidence["controller_response_observed"])

        self.request.stop()

        class Response:
            status = 200
            def read(self, _limit=-1):
                return b'{"result":{"totalApNum":2}}'
            def getheader(self, _name, default=""):
                return "application/json"

        class VerifiedConnection:
            _omada_tls_verified = True
            def request(self, *_args, **_kwargs):
                pass
            def getresponse(self):
                return Response()
            def close(self):
                pass

        with patch.object(self.client, "_connection", return_value=VerifiedConnection()):
            self.client.read_site_overview(SITE)
        live_evidence = self.evidence("site_overview")
        self.assertEqual(live_evidence["response_shape_state"],
                         "response_shape_supported")
        self.assertEqual(live_evidence["support_state"], "live_verified_supported")
        self.assertEqual(live_evidence["permission_state"], "allowed")
        self.assertTrue(live_evidence["controller_response_observed"])

    def test_rrm_missing_or_invalid_core_is_not_support_evidence(self):
        for result in ({}, {"mode": 7, "timeRangeEnable": "false", "resource": 8,
                           "timeRangeAction": -1, "timeRangeId": "private"}):
            with self.subTest(result=result):
                self.payload = {"result": result}
                projected = self.client.read_rrm_settings(SITE)
                self.assertTrue(projected["partial"])
                evidence = self.evidence("rrm_settings")
                self.assertEqual(evidence["result"], "success")
                self.assertEqual(evidence["permission_state"], "unknown")
                self.assertFalse(evidence["controller_response_observed"])
                self.assertEqual(evidence["support_state"], "unknown")
                self.assertEqual(evidence["observation"], "response_partial")
                self.assertEqual(evidence["hardware_support_state"], "unknown")
                self.assertEqual(evidence["firmware_support_state"], "unknown")

    def test_rrm_valid_core_counts_despite_intentional_time_range_redaction(self):
        self.payload = {"result": {"mode": 1, "timeRangeEnable": True,
                                    "resource": 2, "timeRangeAction": 0,
                                    "timeRangeId": "private-range-id"}}
        projected = self.client.read_rrm_settings(SITE)
        self.assertTrue(projected["partial"])
        self.assertEqual(projected["omitted_fields"], ["timeRangeId"])
        evidence = self.evidence("rrm_settings")
        self.assertEqual(evidence["result"], "success")
        self.assertEqual(evidence["permission_state"], "unknown")
        self.assertFalse(evidence["controller_response_observed"])
        self.assertEqual(evidence["response_shape_state"], "response_shape_supported")
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertNotIn("private-range-id", str(evidence))

    def test_rrm_malformed_redacted_time_range_id_is_not_verified(self):
        self.payload = {"result": {"mode": 1, "timeRangeEnable": False,
                                    "resource": 2, "timeRangeAction": 0,
                                    "timeRangeId": 17}}
        projected = self.client.read_rrm_settings(SITE)
        self.assertNotIn("timeRangeId", projected)
        evidence = self.evidence("rrm_settings")
        self.assertEqual(evidence["permission_state"], "unknown")
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["observation"], "response_partial")

    def test_site_overview_empty_projection_is_unknown_but_valid_metrics_are_supported(self):
        self.payload = {"errorCode": 0, "result": {}}
        self.assertEqual(self.client.read_site_overview(SITE)["data"], {})
        evidence = self.evidence("site_overview")
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["observation"], "response_incomplete")
        self.assertEqual(evidence["permission_state"], "unknown")

        self.payload = {"result": {"totalApNum": 0}}
        self.assertEqual(self.client.read_site_overview(SITE)["data"], {"aps_total": 0})
        overview_evidence = self.evidence("site_overview")
        self.assertEqual(overview_evidence["support_state"], "unknown")
        self.assertEqual(overview_evidence["response_shape_state"], "response_shape_supported")
        self.assertFalse(overview_evidence["controller_response_observed"])

    def test_ap_rf_scan_distinguishes_absent_band_keys_from_valid_empty_arrays(self):
        self.payload = {"errorCode": 0, "result": {}}
        response = self.client.read_ap_rf_scan(SITE, AP)
        self.assertEqual(response["data"], {"2g": [], "5g": [], "5g2": [], "6g": []})
        self.assertNotIn("_capability_payload_complete", response)
        self.assertEqual(response["missing_bands"], ["2g", "5g", "5g2", "6g"])
        self.assertTrue(response["partial"])
        evidence = self.evidence("ap_rf_scan")
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["observation"], "response_partial")

        self.payload = {"errorCode": 0, "result": {"channel2g": []}}
        response = self.client.read_ap_rf_scan(SITE, AP)
        self.assertEqual(response["data"], {"2g": [], "5g": [], "5g2": [], "6g": []})
        self.assertEqual(response["missing_bands"], ["5g", "5g2", "6g"])
        self.assertTrue(response["partial"])
        self.assertEqual(self.evidence("ap_rf_scan")["support_state"], "unknown")

        self.payload = {"errorCode": 0, "result": {"channel2g": None, "channel5g": [],
                                    "channel5g2": [], "channel6g": []}}
        with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
            self.client.read_ap_rf_scan(SITE, AP)
        self.assertEqual(self.evidence("ap_rf_scan")["support_state"], "unknown")

        self.payload = {"errorCode": 0, "result": {"channel2g": [], "channel5g": [],
                                    "channel5g2": [], "channel6g": []}}
        response = self.client.read_ap_rf_scan(SITE, AP)
        self.assertNotIn("partial", response)
        self.assertNotIn("missing_bands", response)
        scan_evidence = self.evidence("ap_rf_scan")
        self.assertEqual(scan_evidence["support_state"], "unknown")
        self.assertEqual(scan_evidence["response_shape_state"], "response_shape_supported")
        self.assertFalse(scan_evidence["controller_response_observed"])

    def test_nested_partial_projection_is_unknown_with_successful_permission(self):
        self.payload = {"result": {"futureExtension": "discarded"}}
        self.client.read_ap_mesh_statistics(SITE, AP)
        evidence = self.evidence("ap_mesh_statistics")
        self.assertEqual(evidence["result"], "success")
        self.assertEqual(evidence["permission_state"], "unknown")
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["observation"], "response_partial")

    def test_generic_empty_data_dict_is_incomplete_but_empty_inventory_is_valid(self):
        self.payload = {"errorCode": 0, "result": {}}
        result = self.client.read_controller_health()
        self.assertEqual(result["data"], {})
        evidence = self.evidence("controller_health")
        self.assertEqual(evidence["result"], "success")
        self.assertEqual(evidence["permission_state"], "unknown")
        self.assertEqual(evidence["support_state"], "unknown")
        self.assertEqual(evidence["observation"], "response_incomplete")

        with patch.object(self.client, "_read_pages", return_value=[]):
            inventory = self.client.list_devices(SITE)
        self.assertEqual(inventory["items"], [])
        device_evidence = self.evidence("devices")
        self.assertEqual(device_evidence["support_state"], "unknown")
        self.assertEqual(device_evidence["response_shape_state"], "response_shape_supported")
        self.assertFalse(device_evidence["controller_response_observed"])


if __name__ == "__main__":
    unittest.main()
