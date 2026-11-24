from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_afc_changes import ApAfcChangeError, ApAfcPlans
from app.dpi_changes import SiteDpiLoggingChangeError, SiteDpiLoggingPlans
from app.openapi import OmadaOpenApiClient, OpenApiConfig


SITE = "a" * 24
DEVICE = "b" * 24


class PartialControllerReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE] = "site-id"
        self.client._device_macs_by_site_ref[SITE] = {DEVICE: "00:11:22:33:44:55"}

    def test_dpi_read_keeps_reported_field_partial_and_preview_stays_blocked(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"dpi": True}}):
            result = self.client.read_site_dpi_logging(SITE)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["data"], {"dpi": True, "loggingTraffic": None})
        self.assertEqual(result["missing_field_count"], 1)
        writes = []
        plan = SiteDpiLoggingPlans(lambda _site: result["data"],
                                   lambda *args: writes.append(args))
        with self.assertRaisesRegex(SiteDpiLoggingChangeError, "readback_unavailable"):
            plan.preview(SITE, {"dpi": False}, disruption_confirmed=True)
        self.assertEqual(writes, [])

    def test_afc_read_keeps_reported_support_partial_and_preview_stays_blocked(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"supportAfc": True}}):
            result = self.client.read_ap_afc(SITE, DEVICE)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["data"], {"supportAfc": True, "enable": None})
        self.assertEqual(result["missing_field_count"], 1)
        writes = []
        plan = ApAfcPlans(lambda _site, _device: result["data"],
                          lambda *args: writes.append(args))
        with self.assertRaisesRegex(ApAfcChangeError, "afc_state_invalid"):
            plan.preview(SITE, DEVICE, {"enable": True}, disruption_confirmed=True)
        self.assertEqual(writes, [])


if __name__ == "__main__":
    unittest.main()
