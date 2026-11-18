from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ApOverviewReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.ap_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._device_macs_by_site_ref[self.site_ref] = {self.ap_ref: "00-11-22-33-44-55"}

    def test_projects_diagnostic_summary_and_redacts_identity_fields(self) -> None:
        paths = []
        def request(method, path, **kwargs):
            paths.append((method, path))
            return {"result": {"model": "EAP650", "firmwareVersion": "1.2.3",
                "cpuUtil": 13, "memoryUtil": 44, "uptimeLong": 123456,
                "status": 15, "statusCategory": 1, "wirelessLinked": True,
                "mac": "00-11-22-33-44-55", "ip": "192.0.2.1", "name": "Secret AP",
                "ipv6List": ["2001:db8::1"], "wireless uplink info": {"name": "private"}}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_ap_overview(self.site_ref, self.ap_ref)
        self.assertEqual(paths, [("GET", "/openapi/v1/ctrl/sites/site_1/aps/00-11-22-33-44-55")])
        self.assertEqual(result["data"], {"device_ref": self.ap_ref, "model": "EAP650",
            "firmware": "1.2.3", "cpu_percent": 13, "memory_percent": 44,
            "uptime_seconds": 123456, "status_code": 15, "status_category": 1,
            "wireless_linked": True})
        for secret in ("00-11-22-33-44-55", "192.0.2.1", "Secret AP", "2001:db8::1", "private"):
            self.assertNotIn(secret, str(result))

    def test_rejects_unknown_refs_and_invalid_diagnostic_values(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
            self.client.read_ap_overview(self.site_ref, "c" * 24)
        for response in ({"result": {"cpuUtil": 101}}, {"result": {"status": 99}},
                         {"result": {"wirelessLinked": "yes"}}):
            with patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value=response):
                with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                    self.client.read_ap_overview(self.site_ref, self.ap_ref)

    def test_fixed_allowlist_accepts_only_get_ap_overview(self) -> None:
        path = "/openapi/v1/ctrl/sites/site_1/aps/00-11-22-33-44-55"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("POST", path)


if __name__ == "__main__":
    unittest.main()
