from __future__ import annotations

import unittest
from unittest.mock import call, patch

from app.ap_mesh_candidates import ApMeshCandidatesError, summarize_ap_mesh_candidates


class ApMeshCandidateProjectionTests(unittest.TestCase):
    def test_aggregates_candidate_codes_and_redacts_ap_identity(self):
        result = summarize_ap_mesh_candidates({
            "totalRows": 2, "currentPage": 1, "currentSize": 2,
            "data": [
                {"mac": "AA:BB:CC:DD:EE:FF", "name": "private AP", "linkStatus": 2,
                 "hop": 1, "childsnum": 3, "recommend": True, "recommendRadioId": 0,
                 "multiBandInfo": [{"radioId": 0, "channel": 36, "rssi": -55},
                                   {"radioId": 1, "channel": 149, "rssi": -70}]},
                {"mac": "00:11:22:33:44:55", "name": "another private AP",
                 "linkStatus": 4, "hop": 2, "childsnum": 0, "recommend": False,
                 "recommendRadioId": 1, "multiBandInfo": []},
            ],
        })
        self.assertEqual(result["link_status_counts"], {2: 1, 4: 1})
        self.assertEqual(result["hop_counts"], {1: 1, 2: 1})
        self.assertEqual(result["child_ap_total"], 3)
        self.assertEqual(result["recommended_count"], 1)
        self.assertEqual(result["not_recommended_count"], 1)
        self.assertEqual(result["recommended_radio_id_counts"], {0: 1, 1: 1})
        self.assertEqual(result["radio_id_counts"], {0: 1, 1: 1})
        self.assertEqual(result["channel_counts"], {36: 1, 149: 1})
        self.assertEqual(result["rssi_value_counts"], {-70: 1, -55: 1})
        self.assertEqual(result["redacted_field_count"], 4)
        self.assertFalse(result["partial"])
        for private in ("AA:BB:CC:DD:EE:FF", "00:11:22:33:44:55",
                        "private AP", "another private AP"):
            self.assertNotIn(private, repr(result))

    def test_missing_invalid_and_unknown_values_are_counted(self):
        result = summarize_ap_mesh_candidates({
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
            "data": [{"linkStatus": 7, "hop": True, "childsnum": -1,
                      "recommend": 1, "multiBandInfo": [{"rssi": "private"}],
                      "vendorField": "private-value"}],
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 5)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["missing_field_count"], 2)
        self.assertNotIn("private-value", repr(result))
        self.assertNotIn("private", repr(result))

    def test_unknown_grid_fields_mark_the_projection_partial(self):
        result = summarize_ap_mesh_candidates({
            "totalRows": 0, "currentPage": 1, "currentSize": 0,
            "data": [], "vendorEnvelope": "private-value",
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private-value", repr(result))

    def test_rejects_invalid_and_oversized_grid_shapes(self):
        for value in (None, [], {"totalRows": True, "currentPage": 1,
                                 "currentSize": 0, "data": []},
                      {"totalRows": 2001, "currentPage": 1,
                       "currentSize": 0, "data": []},
                      {"totalRows": 1, "currentPage": True,
                       "currentSize": 0, "data": []}):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(ApMeshCandidatesError):
                    summarize_ap_mesh_candidates(value)
        oversized_bands = summarize_ap_mesh_candidates({
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
            "data": [{"multiBandInfo": [None] * 17}],
        })
        self.assertTrue(oversized_bands["partial"])
        self.assertEqual(oversized_bands["invalid_field_count"], 1)


class ApMeshCandidateClientTests(unittest.TestCase):
    def test_uses_fixed_pages_and_bound_ap_reference(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64, page_size=10, max_pages=2))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site-1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        payloads = [
            {"errorCode": 0, "result": {"totalRows": 2, "currentPage": 1,
             "currentSize": 10, "data": [{"linkStatus": 0, "hop": 1, "childsnum": 0,
             "recommend": True, "multiBandInfo": []}]}},
            {"errorCode": 0, "result": {"totalRows": 2, "currentPage": 2,
             "currentSize": 1, "data": [{"linkStatus": 2, "hop": 2, "childsnum": 1,
             "recommend": False, "multiBandInfo": []}]}},
        ]
        path = "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/grid/mesh/candiParents"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=payloads) as request:
            result = client.read_ap_mesh_candidates(site_ref, ap_ref)
        self.assertEqual(request.call_args_list, [
            call("GET", path + "?page=1&pageSize=10", token="token"),
            call("GET", path + "?page=2&pageSize=10", token="token"),
        ])
        self.assertEqual(result["resource"], "ap_mesh_candidates")
        self.assertEqual(result["total_rows"], 2)
        self.assertEqual(result["recommended_count"], 1)
        with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
            with patch.object(client, "_access_token", return_value="token"), \
                    patch.object(client, "_request_json", return_value={"errorCode": -39303}):
                client.read_ap_mesh_candidates(site_ref, ap_ref)

    def test_request_guard_rejects_unlisted_mesh_paths(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64, page_size=10, max_pages=2))
        with patch.object(client, "_connection") as connection:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json(
                    "GET", "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/"
                    "grid/mesh/candiParents?page=99&pageSize=11")
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
