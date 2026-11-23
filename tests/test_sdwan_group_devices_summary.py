import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SdWanGroupDevicesSummaryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))

    def test_fresh_unique_inventory_binding_and_redacted_device_counts(self):
        group_ref = self.client._opaque_ref("sdwan_group", "ctrl:group-1")
        inventory = [{"id": "group-1", "name": "private-group"}]
        details = {"errorCode": 0, "result": {"port": [
            {"deviceName": "private-device", "deviceMac": "00:11:22:33:44:55",
             "siteId": "private-site", "wanIp": "192.0.2.4", "supportSdWanNat": True},
            {"supportSdWanNat": False},
            {"supportSdWanNat": "unknown"},
        ]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_bounded_grid_rows",
                             return_value=(inventory, 0)) as read_inventory, \
                patch.object(self.client, "_request_json", return_value=details) as request:
            result = self.client.read_controller_sdwan_group_devices_summary(group_ref)
        read_inventory.assert_called_once_with(
            "/openapi/v1/ctrl/sdwan/sdwan-group/brief", "token", 1000)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sdwan/sdwan-group/saved/devices/group-1",
            token="token")
        self.assertEqual(result["reported_device_count"], 3)
        self.assertEqual(result["by_reported_sdwan_nat_capability"],
                         {"true": 1, "false": 1, "unreported": 1})
        for value in ("private-group", "private-device", "00:11:22:33:44:55",
                      "private-site", "192.0.2.4"):
            self.assertNotIn(value, repr(result))
        self.assertTrue(result["partial"])

    def test_refuses_ambiguous_or_truncated_inventory_before_detail_request(self):
        group_ref = self.client._opaque_ref("sdwan_group", "ctrl:group-1")
        for inventory, omitted in (([{"id": "group-1"}, {"id": "group-1"}], 0),
                                   ([{"id": "group-1"}], 1)):
            with patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_read_bounded_grid_rows",
                                 return_value=(inventory, omitted)), \
                    patch.object(self.client, "_request_json") as request:
                with self.assertRaises(OpenApiError):
                    self.client.read_controller_sdwan_group_devices_summary(group_ref)
                request.assert_not_called()

    def test_rejects_unknown_ref_and_enforces_controller_request_guard(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_bounded_grid_rows",
                             return_value=([{"id": "group-1"}], 0)), \
                patch.object(self.client, "_request_json") as request:
            with self.assertRaises(OpenApiError):
                self.client.read_controller_sdwan_group_devices_summary("f" * 24)
            request.assert_not_called()
        self.assertTrue(self.client._controller_sdwan_group_devices_request_valid(
            "/openapi/v1/ctrl/sdwan/sdwan-group/saved/devices/group-1"))
        self.assertFalse(self.client._controller_sdwan_group_devices_request_valid(
            "/openapi/v1/other/sdwan/sdwan-group/saved/devices/group-1"))


if __name__ == "__main__":
    unittest.main()
