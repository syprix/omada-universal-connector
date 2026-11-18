from __future__ import annotations

import unittest
from unittest.mock import patch

from app.device_inventory_summary import (
    DeviceInventorySummaryError,
    summarize_device_inventory,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class DeviceInventoryProjectionTests(unittest.TestCase):
    def test_aggregates_type_and_status_without_returning_identity(self) -> None:
        result = summarize_device_inventory({"data": [
            {"deviceType": "AP", "status": 1, "mac": "00:11:22:33:44:55",
             "name": "private ap", "ip": "192.0.2.1"},
            {"type": "router", "status": 1},
            {"deviceType": "unknown-label", "status": 2},
        ], "totalRows": 3, "currentPage": 1, "currentSize": 3})
        self.assertEqual(result["data"], {
            "device_count": 3,
            "type_counts": {"access_point": 1, "gateway": 1, "switch": 0, "other": 1},
            "status_counts": [{"code": 1, "count": 2}, {"code": 2, "count": 1}],
            "missing_type_count": 0, "missing_status_count": 0,
            "invalid_count": 0, "unknown_field_count": 3,
        })
        self.assertTrue(result["partial"])
        for private in ("00:11:22:33:44:55", "private ap", "192.0.2.1"):
            self.assertNotIn(private, str(result))

    def test_accepts_documented_unpaged_array_and_marks_missing_values_partial(self) -> None:
        result = summarize_device_inventory([{"deviceType": "switch"}])
        self.assertEqual(result["data"]["device_count"], 1)
        self.assertEqual(result["data"]["missing_status_count"], 1)
        self.assertTrue(result["partial"])

    def test_rejects_malformed_or_unbounded_results(self) -> None:
        for value in (None, {}, {"data": [], "totalRows": 1}, ["not-an-object"],
                      [{} for _ in range(5_001)]):
            with self.subTest(value=type(value).__name__), self.assertRaises(DeviceInventorySummaryError):
                summarize_device_inventory(value)
        self.assertEqual(summarize_device_inventory([{"status": True}])["data"]["invalid_count"], 1)


class DeviceInventoryAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_uses_fixed_unpaged_route_bound_to_selected_site(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": [
                    {"deviceType": "AP", "status": 1}]}) as request:
            result = self.client.read_device_inventory_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/devices/all", token="token")
        self.assertEqual(result["resource"], "device_inventory_summary")
        self.assertEqual(result["data"]["device_count"], 1)

    def test_rejects_unknown_site_without_upstream_request(self) -> None:
        with patch.object(self.client, "_request_json") as request, \
                self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_device_inventory_summary("b" * 24)
        request.assert_not_called()

    def test_allowlist_is_controller_bound_and_get_only(self) -> None:
        path = "/openapi/v1/ctrl/sites/site_1/devices/all"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", path.replace("/ctrl/", "/other/"))
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("POST", path)


if __name__ == "__main__":
    unittest.main()
