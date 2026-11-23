from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_stack_ospf_neighbor_summary import summarize_stack_ospf_neighbors
from app.site_stack_static_routing_summary import summarize_stack_static_routes


class StackRoutingSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.config = OpenApiConfig(
            "https://controller.example", "controller_1", "client", "secret",
            cert_sha256="a" * 64, reference_key_file=None, page_size=2, max_pages=3,
        )
        self.client = OmadaOpenApiClient(self.config)
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-1"
        self.stack_ref = self.client._opaque_ref("stack", "site-1:stack_1")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_static_route_projection_counts_only_documented_fields(self) -> None:
        result = summarize_stack_static_routes([
            {"ipVersion": 0, "status": True, "destinations": ["secret"],
             "nextHopIp": "secret", "vrfId": "secret"},
            {"ipVersion": 1, "status": False, "mac": "secret"},
            {"ipVersion": 8, "status": "enabled"},
        ], 4, 1)
        self.assertEqual(result["ip_version_counts"], {"ipv4": 1, "ipv6": 1, "unknown": 1})
        self.assertEqual((result["enabled_count"], result["disabled_count"]), (1, 1))
        self.assertEqual(result["omitted_route_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("secret", json.dumps(result))

    def test_ospf_projection_counts_state_presence_without_interpreting_it(self) -> None:
        result = summarize_stack_ospf_neighbors([
            {"state": "FULL/DR", "neighborIp": "secret", "routerId": "secret",
             "neighborInterface": "secret", "processId": "secret"},
            {"state": None},
        ], 2, 0)
        self.assertEqual(result["state_field_reported_count"], 1)
        self.assertFalse(result["state_values_interpreted"])
        self.assertNotIn("FULL", json.dumps(result))
        self.assertNotIn("secret", json.dumps(result))

    def test_static_routes_bind_fresh_stack_and_paginate_with_redaction(self) -> None:
        replies = [
            {"errorCode": 0, "result": {"totalRows": 1, "currentPage": 1,
             "currentSize": 1, "data": [{"id": "stack_1"}]}},
            {"errorCode": 0, "result": {"totalRows": 3, "currentPage": 1,
             "currentSize": 2, "data": [
                 {"ipVersion": 0, "status": True, "destinations": ["private"]},
                 {"ipVersion": 1, "status": False, "nextHopIp": "private"}]}},
            {"errorCode": 0, "result": {"totalRows": 3, "currentPage": 2,
             "currentSize": 1, "data": [{"ipVersion": 0, "status": True}]}},
        ]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=replies) as request:
            result = self.client.read_site_stack_static_routing_summary(
                self.site_ref, self.stack_ref)
        self.assertEqual(result["ip_version_counts"], {"ipv4": 2, "ipv6": 1, "unknown": 0})
        self.assertEqual(result["route_count"], 3)
        self.assertNotIn("private", json.dumps(result))
        self.assertIn("stacks/stack_1/staticRoutings?page=1&pageSize=2",
                      request.call_args_list[1].args[1])
        self.assertIn("staticRoutings?page=2&pageSize=1",
                      request.call_args_list[2].args[1])

    def test_duplicate_stack_inventory_stops_before_selected_grid_read(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"totalRows": 2, "currentPage": 1, "currentSize": 2,
                               "data": [{"id": "stack_1"}, {"id": "stack_1"}]},
                }) as request:
            with self.assertRaises(OpenApiError) as caught:
                self.client.read_site_stack_ospf_neighbor_summary(
                    self.site_ref, self.stack_ref)
        self.assertEqual(caught.exception.code, "stack_inventory_ambiguous")
        self.assertEqual(request.call_count, 1)

    def test_ospf_empty_zero_page_accepts_only_an_empty_result(self) -> None:
        inventory = {"errorCode": 0, "result": {"totalRows": 1, "currentPage": 1,
            "currentSize": 1, "data": [{"id": "stack_1"}]}}
        empty = {"errorCode": 0, "result": {"totalRows": 0, "currentPage": 0,
            "currentSize": 0, "data": []}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[inventory, empty]):
            result = self.client.read_site_stack_ospf_neighbor_summary(
                self.site_ref, self.stack_ref)
        self.assertEqual(result["neighbor_row_count"], 0)
        self.assertTrue(result["coverage_complete"])

    def test_inconsistent_empty_example_with_placeholder_row_is_rejected(self) -> None:
        inventory = {"errorCode": 0, "result": {"totalRows": 1, "currentPage": 1,
            "currentSize": 1, "data": [{"id": "stack_1"}]}}
        malformed = {"errorCode": 0, "result": {"totalRows": 0, "currentPage": 0,
            "currentSize": 0, "data": [{"state": "placeholder"}]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[inventory, malformed]):
            with self.assertRaises(OpenApiError) as caught:
                self.client.read_site_stack_ospf_neighbor_summary(
                    self.site_ref, self.stack_ref)
        self.assertEqual(caught.exception.code, "openapi_response_invalid")

    def test_stack_grid_path_guards_allow_only_bound_bounded_query_paths(self) -> None:
        static_path = ("/openapi/v1/controller_1/sites/site-1/stacks/stack_1/"
                       "staticRoutings?page=2&pageSize=1000")
        ospf_path = ("/openapi/v1/controller_1/sites/site-1/stack/stack_1/"
                     "ospf-neighbors?page=2&pageSize=1000")
        self.assertTrue(self.client._site_stack_static_routings_request_valid(static_path))
        self.assertTrue(self.client._site_stack_ospf_neighbors_request_valid(ospf_path))
        self.assertFalse(self.client._site_stack_static_routings_request_valid(
            static_path + "&searchKey=private"))
        self.assertFalse(self.client._site_stack_ospf_neighbors_request_valid(
            ospf_path.replace("controller_1", "other")))


if __name__ == "__main__":
    unittest.main()
