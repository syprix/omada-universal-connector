import unittest
from unittest.mock import patch

from app.controller_firmware_inventory_summary import (
    ControllerFirmwareInventoryError, summarize_firmware_inventory,
)
from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient


class ControllerFirmwareInventorySummaryTests(unittest.TestCase):
    def test_counts_metadata_coverage_without_returning_values(self):
        rows = [{
            "id": "private-id", "name": "private.bin",
            "modelTypeInfo": {"showModel": "Display Model", "compoundModel": "backend-model"},
            "uploadTime": 1_700_000_000_000, "description": "private description",
        }, {"id": "private-id-2", "modelTypeInfo": {}, "uploadTime": 0}]
        result = summarize_firmware_inventory(rows, 2, 1, 10)
        self.assertEqual(result["firmware_entry_count"], 2)
        self.assertEqual(result["metadata_field_coverage"], {
            "identifier_reported_count": 2, "file_name_reported_count": 1,
            "model_information_reported_count": 2, "display_model_reported_count": 1,
            "backend_model_reported_count": 1, "upload_time_reported_count": 2,
            "description_reported_count": 1,
        })
        self.assertTrue(result["partial"])
        for secret in ("private-id", "private.bin", "Display Model", "backend-model",
                       "private description", "1700000000000"):
            self.assertNotIn(secret, repr(result))

    def test_truncation_and_invalid_rows_are_explicit(self):
        result = summarize_firmware_inventory([None], 2, 1, 10)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["invalid_record_count"], 1)
        self.assertTrue(result["partial"])
        with self.assertRaises(ControllerFirmwareInventoryError):
            summarize_firmware_inventory({}, 0, 0, 10)

    def test_adapter_pages_bounded_list_and_checks_contract_metadata(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=2, max_pages=2))
        pages = [
            {"result": {"totalRows": 3, "currentPage": 1, "currentSize": 2,
                        "data": [{"id": "x"}, {"id": "y"}]}},
            {"result": {"totalRows": 3, "currentPage": 2, "currentSize": 2,
                        "data": [{"id": "z"}]}},
        ]
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=pages) as request:
            result = client.read_controller_firmware_inventory_summary()
        self.assertEqual(result["firmware_entry_count"], 3)
        self.assertFalse(result["truncated"])
        self.assertEqual([call.args[1] for call in request.call_args_list], [
            "/openapi/v1/ctrl/upgrade/firmwares?page=1&pageSize=2",
            "/openapi/v1/ctrl/upgrade/firmwares?page=2&pageSize=2",
        ])
        self.assertTrue(client._controller_firmware_list_request_valid(
            "/openapi/v1/ctrl/upgrade/firmwares?page=1&pageSize=100"))
        self.assertFalse(client._controller_firmware_list_request_valid(
            "/openapi/v1/other/upgrade/firmwares?page=1&pageSize=100"))
        self.assertFalse(client._controller_firmware_list_request_valid(
            "/openapi/v1/ctrl/upgrade/firmwares?page=11&pageSize=100"))

    def test_empty_zero_page_is_accepted_only_for_empty_first_page(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "totalRows": 0, "currentPage": 0, "currentSize": 0, "data": []}}):
            self.assertEqual(client.read_controller_firmware_inventory_summary()[
                "firmware_entry_count"], 0)
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "totalRows": 0, "currentPage": 0, "currentSize": 1, "data": [{}]}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                client.read_controller_firmware_inventory_summary()

    def test_empty_grid_reports_page_capacity_not_returned_rows(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100))
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "totalRows": 0, "currentPage": 1, "currentSize": 100, "data": []}}):
            result = client.read_controller_firmware_inventory_summary()
        self.assertEqual(result["firmware_entry_count"], 0)
        self.assertTrue(result["coverage_complete"])
        self.assertFalse(result["partial"])


if __name__ == "__main__":
    unittest.main()
