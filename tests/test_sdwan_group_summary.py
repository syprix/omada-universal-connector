import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.sdwan_group_summary import summarize_sdwan_group_rows


class SdWanGroupSummaryTests(unittest.TestCase):
    def test_projects_only_counts_and_redacts_group_and_hub_values(self) -> None:
        result = summarize_sdwan_group_rows([
            {"id": "private-group-1", "name": "private-name-1",
             "hubDeviceType": "private-hub-type", "hubModel": "private-model",
             "hubModelVersion": "private-version", "deviceNum": 3},
            {"id": "private-group-2", "name": "private-name-2",
             "hubDeviceType": "private-hub-type-2", "hubModel": "private-model-2",
             "hubModelVersion": "private-version-2", "deviceNum": 4},
        ])
        self.assertEqual(result["returned_group_count"], 2)
        self.assertEqual(result["reported_group_total"], 2)
        self.assertEqual(result["reported_group_device_membership_sum"], 7)
        self.assertEqual(result["field_coverage"]["hub_model_version"],
                         {"reported": 2, "unreported": 0})
        self.assertFalse(result["partial"])
        for secret in ("private-group-1", "private-name-1", "private-hub-type",
                       "private-model", "private-version"):
            self.assertNotIn(secret, repr(result))

    def test_missing_fields_invalid_rows_unknown_fields_and_omission_are_partial(self) -> None:
        result = summarize_sdwan_group_rows([
            {"deviceNum": -1, "unexpected": "redacted-value"}, None,
        ], omitted_rows=5)
        self.assertEqual(result["omitted_group_count"], 5)
        self.assertEqual(result["invalid_rows"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["field_coverage"]["device_count"],
                         {"reported": 0, "unreported": 2})
        self.assertNotIn("redacted-value", repr(result))
        self.assertTrue(result["partial"])

    def test_client_uses_controller_scoped_bounded_endpoint(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_read_bounded_grid_rows", return_value=(
                    [{"hubDeviceType": "gateway", "deviceNum": 8}], 2)) as request:
            result = client.read_controller_sdwan_group_summary()
        request.assert_called_once_with(
            "/openapi/v1/ctrl/sdwan/sdwan-group/brief", "token", 1000)
        self.assertEqual(result["reported_group_total"], 3)
        self.assertEqual(result["reported_group_device_membership_sum"], 8)
        self.assertEqual(result["omitted_group_count"], 2)
        self.assertTrue(result["partial"])

    def test_inventory_returns_only_opaque_refs_for_unique_group_ids(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_read_bounded_grid_rows", return_value=(
                    [{"id": "private-group", "name": "private-name", "deviceNum": 1}], 0)):
            result = client.read_controller_sdwan_group_summary()
        self.assertEqual(result["group_ref_count"], 1)
        self.assertRegex(result["group_refs"][0], r"^[0-9a-f]{24}$")
        self.assertNotIn("private-group", repr(result))
        self.assertNotIn("private-name", repr(result))

    def test_request_guard_binds_controller_and_limits_pagination(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        self.assertTrue(client._controller_sdwan_group_brief_request_valid(
            "/openapi/v1/ctrl/sdwan/sdwan-group/brief?page=10&pageSize=1000"))
        self.assertFalse(client._controller_sdwan_group_brief_request_valid(
            "/openapi/v1/other/sdwan/sdwan-group/brief?page=1&pageSize=100"))
        self.assertFalse(client._controller_sdwan_group_brief_request_valid(
            "/openapi/v1/ctrl/sdwan/sdwan-group/brief?page=11&pageSize=100"))
        self.assertFalse(client._controller_sdwan_group_brief_request_valid(
            "/openapi/v1/ctrl/sdwan/sdwan-group/brief?page=1&pageSize=1001"))


if __name__ == "__main__":
    unittest.main()
