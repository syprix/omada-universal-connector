from __future__ import annotations

import unittest

from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient
from app.site_capabilities import FIELDS
from app.site_capability_comparison import (
    SiteCapabilityComparisonError, project_site_capability_comparison,
)


class SiteCapabilityComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_a, self.site_b, self.site_c = "a" * 24, "b" * 24, "c" * 24

    def test_projector_preserves_unknowns_and_separates_permission_errors(self) -> None:
        result = project_site_capability_comparison(
            [self.site_a, self.site_b],
            {
                self.site_a: {"status": "ok", "resource": "site_capabilities",
                              "site_ref": self.site_a, "partial": False,
                              "data": {"capabilities": {"firewall": True,
                                                          "wireguard": False}}},
                self.site_b: {"status": "error", "error": "openapi_permission_denied"},
            })
        self.assertEqual(result["feature_columns"], sorted(FIELDS.values()))
        index = result["feature_columns"].index("firewall")
        self.assertEqual(result["feature_values"][index], [1, None])
        self.assertEqual(result["sites"][0]["unknown_count"], len(FIELDS) - 2)
        self.assertEqual(result["sites"][1]["error"], "openapi_permission_denied")
        self.assertTrue(result["partial"])

    def test_reader_refreshes_inventory_and_reads_only_selected_current_sites(self) -> None:
        self.client._site_ids_by_ref = {self.site_a: "old-a", self.site_b: "old-b"}
        seen = []

        def inventory():
            self.client._site_ids_by_ref = {self.site_a: "site-a", self.site_b: "site-b"}
            return {"status": "ok", "items": [
                {"site_ref": self.site_a}, {"site_ref": self.site_b}]}

        def read(ref):
            seen.append(ref)
            if ref == self.site_b:
                raise OpenApiError("openapi_permission_denied")
            return {"status": "ok", "resource": "site_capabilities", "site_ref": ref,
                    "partial": False, "data": {"capabilities": {"firewall": True}}}

        self.client.list_sites = inventory
        self.client.read_site_capabilities = read
        result = self.client.read_site_capability_comparison(
            [self.site_a, self.site_b, self.site_c])
        self.assertEqual(seen, [self.site_a, self.site_b])
        self.assertEqual(result["sites"][0]["status"], "ok")
        self.assertEqual([row["error"] for row in result["sites"][1:]],
                         ["openapi_permission_denied", "site_ref_unknown"])

    def test_reader_rejects_duplicate_or_unbounded_site_refs(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "site_refs_invalid"):
            self.client.read_site_capability_comparison([self.site_a, self.site_a])
        with self.assertRaisesRegex(OpenApiError, "site_refs_invalid"):
            self.client.read_site_capability_comparison([self.site_a] * 17)

    def test_projector_rejects_mismatched_reference_and_duplicate_columns(self) -> None:
        with self.assertRaises(SiteCapabilityComparisonError):
            project_site_capability_comparison([self.site_a, self.site_a], {})
        result = project_site_capability_comparison(
            [self.site_a, self.site_b],
            {self.site_a: {"status": "ok", "resource": "site_capabilities",
                           "site_ref": self.site_b, "data": {"capabilities": {}}}})
        self.assertEqual(result["sites"][0]["status"], "unavailable")
        self.assertEqual(result["sites"][0]["error"], "source_unavailable")


if __name__ == "__main__":
    unittest.main()
