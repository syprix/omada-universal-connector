from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class RadioReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64,
        ))
        self.site_ref = "a" * 24
        self.device_ref = "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._device_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00:11:22:33:44:55"
        }

    def test_schema_accurate_nested_results_are_filtered(self) -> None:
        answers = iter([
            {"result": {"radioSetting2g": {"channel": "6", "channelWidth": "20MHz",
                                            "txPower": 20, "radioEnable": True,
                                            "ssid": "private"},
                         "radioSetting5g1": {"channel": "36", "secret": "private"},
                         "name": "private"}},
            {"result": {"radioTraffic2g": {"rxPkts": 12, "txPkts": 5, "ssid": "private"},
                         "wp2g": {"actualChannel": "6", "txUtil": 3, "mac": "private"},
                         "wp5g2": {"busyUtil": 7, "name": "private"},
                         "raw": "private"}},
            {"result": {"status": 1, "fromGlobal": False, "secret": "private"}},
            {"result": {"channelLoads2g": [{"channel": 1, "load": 2, "ssid": "private"}],
                         "channelLoads5g": [{"channel": 36, "load": 3}],
                         "channelLoads6g": [], "name": "private"}},
        ])
        paths: list[str] = []

        def request(method: str, path: str, **_kwargs: object) -> dict[str, object]:
            self.assertEqual(method, "GET")
            paths.append(path)
            return next(answers)

        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = {part: self.client.read_ap_radio_part(self.site_ref, self.device_ref, part)["data"]
                      for part in ("radio_config", "radios", "scan_status", "channel_load")}
        self.assertEqual(len(paths), 4)
        self.assertTrue(all("00:11:22:33:44:55" in path for path in paths))
        self.assertEqual(result["radio_config"], {
            "radioSetting2g": {"channel": "6", "channelWidth": "20MHz", "txPower": 20,
                                "radioEnable": True},
            "radioSetting5g1": {"channel": "36"},
        })
        self.assertEqual(result["radios"], {
            "radioTraffic2g": {"rxPkts": 12, "txPkts": 5},
            "wp2g": {"actualChannel": "6", "txUtil": 3},
            "wp5g2": {"busyUtil": 7},
        })
        self.assertEqual(result["channel_load"], {
            "channelLoads2g": [{"channel": 1, "load": 2}],
            "channelLoads5g": [{"channel": 36, "load": 3}],
            "channelLoads6g": [],
        })
        self.assertNotIn("private", str(result))

    def test_only_explicit_ap_device_types_are_mapped(self) -> None:
        rows = [
            {"deviceId": "ap-id", "deviceType": "AP", "mac": "00-11-22-33-44-55"},
            {"deviceId": "unknown-id", "deviceType": "router", "mac": "00:11:22:33:44:66"},
            {"deviceId": "maybe-id", "deviceType": "unknown", "mac": "00:11:22:33:44:77",
             "deviceModel": "EAP"},
        ]
        self.client._read_pages = lambda *_args: rows  # type: ignore[method-assign]
        with patch.object(self.client, "_access_token", return_value="token"):
            result = self.client.list_devices(self.site_ref)
        self.assertEqual(len(result["items"]), 3)  # type: ignore[arg-type]
        mapping = self.client._device_macs_by_site_ref[self.site_ref]
        self.assertEqual(list(mapping.values()), ["00-11-22-33-44-55"])

    def test_dash_mac_ap_read_path_passes_allowlist(self) -> None:
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json(
                    "GET", "/openapi/v1/ctrl/sites/site_1/aps/00-11-22-33-44-55/radios"
                )

    def test_site_refresh_preserves_known_ap_mapping(self) -> None:
        actual_ref = self.client._opaque_ref("site", "site_1")
        self.client._device_macs_by_site_ref[actual_ref] = {
            self.device_ref: "00:11:22:33:44:55"
        }
        self.client._read_pages = lambda *_args: [{"siteId": "site_1"}]  # type: ignore[method-assign]
        with patch.object(self.client, "_access_token", return_value="token"):
            self.client.list_sites()
        self.assertEqual(
            self.client._device_macs_by_site_ref[actual_ref][self.device_ref],
            "00:11:22:33:44:55",
        )

    def test_unknown_refs_and_malformed_or_large_entities_fail(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
            self.client.read_ap_radio_part(self.site_ref, "c" * 24, "radios")
        for part, payload in (
            ("radio_config", {"result": []}),
            ("channel_load", {"result": {"channelLoads2g": [{"channel": 1, "load": 2}] * 65}}),
        ):
            with patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value=payload):
                with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                    self.client.read_ap_radio_part(self.site_ref, self.device_ref, part)
        with self.assertRaisesRegex(OpenApiError, "ap_radio_part_invalid"):
            self.client.read_ap_radio_part(self.site_ref, self.device_ref, "delete")

    def test_unapproved_path_still_rejected(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", "/openapi/v1/ctrl/sites/site_1/aps/evil/radios")


if __name__ == "__main__":
    unittest.main()
