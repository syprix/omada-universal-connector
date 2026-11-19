from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SiteChannelReuseIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.refs = [self.client._opaque_ref("device", "site_1:ap-1"),
                     self.client._opaque_ref("device", "site_1:ap-2")]
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_fresh_inventory_bound_radio_and_existing_load_reads_are_joined(self):
        inventory = [
            {"deviceId": "ap-1", "deviceType": "AP", "mac": "00:11:22:33:44:55"},
            {"deviceId": "ap-2", "deviceType": "AP", "mac": "00:11:22:33:44:66"},
        ]
        self.client._read_pages = lambda *_args: inventory  # type: ignore[method-assign]
        def request(method: str, path: str, **_kwargs: object) -> dict[str, object]:
            self.assertEqual(method, "GET")
            if path.endswith("/radios"):
                channel = "6" if "55" in path else "6"
                return {"result": {"wp2g": {"actualChannel": channel, "bandWidth": "20MHz"}}}
            if path.endswith("/full-channel-detect/channel-load"):
                return {"result": {"channelLoads2g": [{"channel": 6, "load": 27}],
                                    "channelLoads5g": [], "channelLoads6g": []}}
            self.fail("unexpected upstream path")
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_site_channel_reuse_summary(self.site_ref, self.refs)
        self.assertEqual(result["resource"], "site_channel_reuse_summary")
        self.assertEqual(result["same_channel_reuse"][0]["access_point_count"], 2)
        self.assertEqual(result["access_points"][0]["bands"][0]["reported_channel_load"], 27)

    def test_selected_reference_must_be_in_fresh_inventory(self):
        self.client._read_pages = lambda *_args: []  # type: ignore[method-assign]
        with patch.object(self.client, "_access_token", return_value="token"):
            with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
                self.client.read_site_channel_reuse_summary(self.site_ref, self.refs[:1])

    def test_input_size_and_duplicates_are_rejected(self):
        with self.assertRaisesRegex(OpenApiError, "device_refs_invalid"):
            self.client.read_site_channel_reuse_summary(self.site_ref, ["b" * 24] * 2)
        with self.assertRaisesRegex(OpenApiError, "device_refs_invalid"):
            self.client.read_site_channel_reuse_summary(self.site_ref, ["b" * 24] * 17)
