from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class DeviceFirmwareReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.device_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_maps_inventory_device_ref_to_read_only_firmware_path(self) -> None:
        self.client._read_pages = lambda *_args: [{"deviceId": "opaque-source-id",
            "deviceType": "Switch", "mac": "00-11-22-33-44-55", "name": "private",
            "ip": "192.0.2.1"}]
        with patch.object(self.client, "_access_token", return_value="token"):
            listing = self.client.list_devices(self.site_ref)
        ref = listing["items"][0]["device_ref"]
        paths = []
        def request(method, path, **kwargs):
            paths.append((method, path))
            return {"result": {"curFwVer": "3.0.1 Build 20260101 Rel.12345",
                                "lastFwVer": "3.1.0", "fwReleaseLog": "private URL/name"}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_device_firmware(self.site_ref, ref)
        self.assertEqual(paths, [("GET", "/openapi/v1/ctrl/sites/site_1/devices/00-11-22-33-44-55/latest-firmware-info")])
        self.assertEqual(result["device_ref"], ref)
        self.assertEqual(result["data"], {"current_version": "3.0.1 Build 20260101 Rel.12345",
                                          "latest_version": "3.1.0", "versions_differ": True, "update_available": None})
        for forbidden in ("00-11-22-33-44-55", "192.0.2.1", "private", "fwReleaseLog"):
            self.assertNotIn(forbidden, str(result))
        capability = next(item for item in self.client.capabilities()["items"]
                          if item["operation"] == "device_firmware")
        self.assertEqual(capability["runtime_evidence"][0]["target_ref"], self.site_ref + ":" + ref)

    def test_requires_known_ref_and_redacts_or_rejects_unsafe_versions(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
            self.client.read_device_firmware(self.site_ref, self.device_ref)
        self.client._inventory_macs_by_site_ref[self.site_ref] = {self.device_ref: "00:11:22:33:44:55"}
        for unsafe in ("https://vendor.example/fw", "192.0.2.1", "1.2.3/../../secret",
                       "2.0.1 Build 192.0.2.1"):
            with patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": {"lastFwVer": unsafe}}):
                with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                    self.client.read_device_firmware(self.site_ref, self.device_ref)

    def test_update_availability_requires_both_versions(self) -> None:
        self.client._inventory_macs_by_site_ref[self.site_ref] = {self.device_ref: "00:11:22:33:44:55"}
        for versions, expected in (({"curFwVer": "1.0", "lastFwVer": "1.0"}, False),
                                   ({"curFwVer": "1.0"}, None)):
            with patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": versions}):
                result = self.client.read_device_firmware(self.site_ref, self.device_ref)
            self.assertIs(result["data"]["versions_differ"], expected)
            self.assertIsNone(result["data"]["update_available"])

    def test_fixed_allowlist_accepts_only_get_firmware_info(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/devices/00-11-22-33-44-55/latest-firmware-info"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("POST", allowed)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", allowed + "/start-online-upgrade")


if __name__ == "__main__":
    unittest.main()
