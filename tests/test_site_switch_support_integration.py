from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_switch_support import FIELDS


class SiteSwitchSupportIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_reads_exact_documented_route_and_projects_both_flags(self) -> None:
        raw = {field: (field == "supportES") for field in FIELDS}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_site_switch_support(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/switch-support", token="token")
        self.assertEqual(result["resource"], "site_switch_support")
        self.assertEqual(result["data"]["switch_support"],
                         {"support_es": True, "support_l2": False})
        self.assertFalse(result["partial"])
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "site_switch_support")["runtime_evidence"][0]
        self.assertFalse(evidence["controller_response_observed"])
        self.assertEqual(evidence["permission_state"], "unknown")
        self.assertEqual(evidence["support_state"], "unknown")

    def test_requires_known_site_and_rejects_invalid_response(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "site_ref_invalid"):
            self.client.read_site_switch_support("site")
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_switch_support("b" * 24)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_switch_support(self.site_ref)

    def test_rejects_other_controller_path(self) -> None:
        good = "/openapi/v1/ctrl/sites/site_1/switch-support"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))


if __name__ == "__main__":
    unittest.main()
