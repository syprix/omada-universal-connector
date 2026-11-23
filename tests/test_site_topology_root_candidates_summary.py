from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_topology_root_candidates_summary import (
    TopologyRootCandidatesError, summarize_topology_root_candidates,
)


class TopologyRootCandidatesSummaryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_counts_documented_types_flags_and_specific_type_redacted(self):
        result = summarize_topology_root_candidates([
            {"type": "switch", "specificType": 0, "name": "private",
             "mac": "private", "isRoot": True, "stackGroup": False},
            {"type": "other", "specificType": 1, "clientType": "private",
             "isRoot": False, "stackGroup": True},
            {"type": "olt"},
        ])
        self.assertEqual(result["root_candidate_count"], 3)
        self.assertEqual(result["node_type_counts"],
                         {"switch": 1, "olt": 1, "other": 1, "unknown": 0})
        self.assertEqual(result["specific_type_counts"]["mlag"], 1)
        self.assertEqual(result["specific_type_counts"]["vrrp"], 1)
        for secret in ("private", "clientType", "AA-BB"):
            self.assertNotIn(secret, repr(result))
        self.assertFalse(result["partial"])

    def test_unknown_types_and_fields_are_visible_as_partial(self):
        result = summarize_topology_root_candidates([
            {"type": "new-type", "futureField": True},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["node_type_counts"]["unknown"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        with self.assertRaises(TopologyRootCandidatesError):
            summarize_topology_root_candidates({"result": []})

    def test_site_bound_http_projection_has_no_topology_links(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": [
                    {"type": "switch", "mac": "private", "isRoot": True}]}) as request:
            result = self.client.read_site_topology_root_candidates_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v2/ctrl/sites/site_internal/topology/nodes", token="token")
        self.assertNotIn("links", result)
        self.assertNotIn("private", repr(result))
        self.assertTrue(self.client._site_topology_root_candidates_request_valid(
            "/openapi/v2/ctrl/sites/site_internal/topology/nodes"))
        self.assertFalse(self.client._site_topology_root_candidates_request_valid(
            "/openapi/v2/other/sites/site_internal/topology/nodes"))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_topology_root_candidates_summary("7" * 24)


if __name__ == "__main__":
    unittest.main()
