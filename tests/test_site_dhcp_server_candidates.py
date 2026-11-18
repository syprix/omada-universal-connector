from __future__ import annotations

import unittest
from unittest.mock import call, patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_dhcp_server_candidates import (
    SiteDhcpCandidatesError, project_site_dhcp_candidates,
)


def page(number: int, total: int, rows: list[dict[str, object]]) -> dict[str, object]:
    return {"totalRows": total, "currentPage": number,
            "currentSize": len(rows), "data": rows}


def candidate(index: int) -> dict[str, object]:
    return {"mac": f"private-mac-{index}", "name": f"private-device-{index}",
            "stackId": f"private-stack-{index}", "ip": f"192.0.2.{index % 200 + 1}",
            "ports": [{"portId": f"private-port-{index}"}],
            "impbs": [{"vlan": index}]}


class SiteDhcpCandidateProjectionTests(unittest.TestCase):
    def test_counts_rows_and_omits_all_device_details(self) -> None:
        result = project_site_dhcp_candidates([page(1, 2, [candidate(1), candidate(2)])])
        self.assertEqual(result["data"]["reported_total_candidate_count"], 2)
        self.assertEqual(result["data"]["returned_candidate_count"], 2)
        self.assertEqual(result["data"]["valid_candidate_record_count"], 2)
        self.assertFalse(result["partial"])
        for secret in ("private-mac", "private-device", "private-stack", "192.0.2.",
                       "private-port", "vlan"):
            self.assertNotIn(secret, repr(result))

    def test_marks_malformed_pages_and_truncated_limit(self) -> None:
        malformed = project_site_dhcp_candidates([{"data": [None]}])
        self.assertTrue(malformed["partial"])
        self.assertEqual(malformed["invalid_field_count"], 1)
        capped = project_site_dhcp_candidates([
            page(i, 600, [candidate(i * 100 + j) for j in range(100)])
            for i in range(1, 6)])
        self.assertEqual(capped["data"]["returned_candidate_count"], 500)
        self.assertTrue(capped["data"]["truncated"])

    def test_rejects_unbounded_outer_shape(self) -> None:
        for value in (None, [], [page(i, 0, []) for i in range(6)]):
            with self.subTest(shape=type(value).__name__), self.assertRaises(SiteDhcpCandidatesError):
                project_site_dhcp_candidates(value)


class SiteDhcpCandidateClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_pages_and_projects_count_only(self) -> None:
        responses = [{"result": page(1, 101, [candidate(i) for i in range(100)])},
                     {"result": page(2, 101, [candidate(101)])}]
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", side_effect=responses) as request:
            result = self.client.read_site_dhcp_candidate_summary(self.site_ref)
        self.assertEqual(request.call_args_list, [
            call("GET", "/openapi/v1/ctrl/sites/site_internal/networks/devices?page=1&pageSize=100", token="test-token"),
            call("GET", "/openapi/v1/ctrl/sites/site_internal/networks/devices?page=2&pageSize=100", token="test-token"),
        ])
        self.assertEqual(result["data"]["returned_candidate_count"], 101)
        self.assertFalse(result["partial"])
        self.assertNotIn("private-mac", repr(result))

    def test_path_guard_and_unknown_site(self) -> None:
        self.assertTrue(self.client._site_dhcp_candidates_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/networks/devices?page=5&pageSize=100"))
        self.assertFalse(self.client._site_dhcp_candidates_request_valid(
            "/openapi/v1/other/sites/site_internal/networks/devices?page=1&pageSize=100"))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_dhcp_candidate_summary("7" * 24)


if __name__ == "__main__":
    unittest.main()
