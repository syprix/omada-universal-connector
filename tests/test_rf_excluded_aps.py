from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.rf_excluded_aps import RfExcludedApsError, project_rf_excluded_aps


class RfExcludedApsTests(unittest.TestCase):
    def test_returns_site_opaque_refs_and_redacts_ap_identity(self) -> None:
        ref = "a" * 24
        result = project_rf_excluded_aps([{
            "mac": "AA:BB:CC:DD:EE:FF", "name": "private-ap", "ip": "192.0.2.5",
            "model": "EAP", "unsupportType": 1, "statusCategory": 1,
            "addedInAdvanced": True,
        }], {"aabbccddeeff": [ref]})
        self.assertEqual(result["items"], [{
            "ap_ref": ref, "unsupported_reason": 1, "status_category": 1,
            "added_in_advanced": True,
        }])
        self.assertFalse(result["partial"])
        for private in ("AA:BB:CC:DD:EE:FF", "private-ap", "192.0.2.5"):
            self.assertNotIn(private, repr(result))

    def test_unknown_ambiguous_and_invalid_rows_are_omitted(self) -> None:
        result = project_rf_excluded_aps([
            {"mac": "00:00:00:00:00:01"},
            {"mac": "AA:BB:CC:DD:EE:FF"},
            {"mac": "invalid"},
        ], {"aabbccddeeff": ["a" * 24, "b" * 24]})
        self.assertEqual(result["items"], [])
        self.assertEqual(result["omitted_field_count"], 3)
        self.assertTrue(result["partial"])

    def test_row_and_collection_limits_fail_closed(self) -> None:
        with self.assertRaises(RfExcludedApsError):
            project_rf_excluded_aps([{}] * 257, {})
        with self.assertRaises(RfExcludedApsError):
            project_rf_excluded_aps([{f"extra{i}": i for i in range(25)}], {})

    def test_full_first_page_is_marked_partial_when_total_is_not_reported(self) -> None:
        row = {"mac": "AA:BB:CC:DD:EE:FF", "unsupportType": 1}
        result = project_rf_excluded_aps([row] * 256, {"aabbccddeeff": ["a" * 24]})
        self.assertEqual(result["count"], 256)
        self.assertTrue(result["page_limit_reached"])
        self.assertTrue(result["partial"])

    def test_reads_live_paged_response_and_marks_omitted_rows_partial(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site_1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA:BB:CC:DD:EE:FF"}
        expected_path = (
            "/openapi/v1/ctrl/sites/site_1/rfPlanning/excludeAps"
            "?currentPage=1&currentPageSize=256")
        def request(method, path, token):
            self.assertEqual((method, path, token), ("GET", expected_path, "token"))
            return {"result": {
                "currentPage": 1, "currentSize": 1, "totalRows": 3,
                "data": [{"mac": "AA:BB:CC:DD:EE:FF", "unsupportType": 1}],
            }}
        with patch.object(client, "list_devices"), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=request):
            result = client.read_rf_excluded_aps(site_ref)
        self.assertEqual(result["count"], 1)
        self.assertTrue(result["partial"])
        self.assertTrue(result["page_limit_reached"])

    def test_rejects_inconsistent_paged_response_count(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref = "a" * 24
        client._site_ids_by_ref[site_ref] = "site_1"
        with patch.object(client, "list_devices"), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "currentPage": 1, "currentSize": 1, "totalRows": 0,
                    "data": [{"mac": "AA:BB:CC:DD:EE:FF"}],
                }}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                client.read_rf_excluded_aps(site_ref)

    def test_unmatched_row_is_partial_without_falsely_reaching_page_limit(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref = "a" * 24
        client._site_ids_by_ref[site_ref] = "site_1"
        client._device_macs_by_site_ref[site_ref] = {}
        with patch.object(client, "list_devices"), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "currentPage": 1, "currentSize": 1, "totalRows": 1,
                    "data": [{"mac": "AA:BB:CC:DD:EE:FF", "unsupportType": 1}],
                }}):
            result = client.read_rf_excluded_aps(site_ref)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["omitted_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertFalse(result["page_limit_reached"])

    def test_complete_full_paged_response_is_not_partial_at_exact_total(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref = "a" * 24
        client._site_ids_by_ref[site_ref] = "site_1"
        rows = []
        macs = {}
        for index in range(256):
            mac = ":".join(f"{byte:02X}" for byte in (2, 0, 0, 0, index // 256, index % 256))
            ap_ref = f"{index + 1:024x}"
            macs[ap_ref] = mac
            rows.append({"mac": mac, "unsupportType": 1})
        client._device_macs_by_site_ref[site_ref] = macs
        with patch.object(client, "list_devices"), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "currentPage": 1, "currentSize": 256, "totalRows": 256, "data": rows,
                }}):
            result = client.read_rf_excluded_aps(site_ref)
        self.assertEqual(result["count"], 256)
        self.assertFalse(result["partial"])
        self.assertFalse(result["page_limit_reached"])

    def test_reads_one_documented_bounded_site_page(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site_1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA:BB:CC:DD:EE:FF"}
        expected_path = (
            "/openapi/v1/ctrl/sites/site_1/rfPlanning/excludeAps"
            "?currentPage=1&currentPageSize=256")
        def request(method, path, token):
            self.assertEqual((method, path, token), ("GET", expected_path, "token"))
            self.assertTrue(client._rf_excluded_aps_request_valid(path))
            return {"result": {"currentPage": 1, "currentSize": 1, "totalRows": 1,
                                "data": [{"mac": "AA:BB:CC:DD:EE:FF", "unsupportType": 1}]}}
        with patch.object(client, "list_devices") as inventory, \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=request):
            result = client.read_rf_excluded_aps(site_ref)
        inventory.assert_called_once_with(site_ref)
        self.assertEqual(result["items"], [{"ap_ref": ap_ref, "unsupported_reason": 1}])
        self.assertFalse(result["partial"])


if __name__ == "__main__":
    unittest.main()
