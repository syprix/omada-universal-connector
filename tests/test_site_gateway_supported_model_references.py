import unittest
from unittest.mock import patch

from app.operation_registry import REGISTRY, RegistryError
from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient
from app.site_gateway_supported_model_references import (
    MAX_MODEL_NAME_LENGTH,
    SiteGatewaySupportedModelReferencesError,
    project_site_gateway_supported_model_references,
)


class SiteGatewaySupportedModelReferencesTests(unittest.TestCase):
    def client(self):
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))

    def test_empty_and_vendor_zero_empty_name_example(self):
        empty = project_site_gateway_supported_model_references({"supportModels": []})
        self.assertEqual(empty["data"]["model_references"], [])
        self.assertTrue(empty["data"]["source_list_present"])
        self.assertFalse(empty["partial"])
        example = project_site_gateway_supported_model_references(
            {"supportModels": [{"id": 0, "name": ""}]})
        self.assertEqual(example["data"]["model_references"],
                         [{"model_id": 0, "model_name": ""}])
        boundary = project_site_gateway_supported_model_references({"supportModels": [
            {"id": -(1 << 31), "name": "low"},
            {"id": (1 << 31) - 1, "name": "high"},
        ]})
        self.assertEqual([row["model_id"] for row in boundary["data"]["model_references"]],
                         [-(1 << 31), (1 << 31) - 1])

    def test_missing_list_is_partial_and_never_reported_as_empty_success(self):
        result = project_site_gateway_supported_model_references({"other": "private"})
        self.assertEqual(result["data"]["model_references"], [])
        self.assertFalse(result["data"]["source_list_present"])
        self.assertEqual(result["data"]["missing_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private", repr(result))

    def test_bad_rows_duplicates_unknown_fields_and_bounded_text_are_partial(self):
        result = project_site_gateway_supported_model_references({"supportModels": [
            {"id": 1, "name": "one"}, {"id": 1, "name": "duplicate"},
            {"id": True, "name": "bool"}, {"id": 2, "name": 7},
            {"id": 3, "name": "x" * (MAX_MODEL_NAME_LENGTH + 1)},
            {"id": 4, "name": "line\nbreak"},
            {"id": 5, "name": "valid", "privateExtra": "must-not-appear"},
            None,
        ], "unknownRoot": "also-private"})
        self.assertEqual(result["data"]["model_references"],
                         [{"model_id": 5, "model_name": "valid"}])
        self.assertEqual(result["data"]["invalid_row_count"], 5)
        self.assertEqual(result["data"]["duplicate_model_id_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 2)
        self.assertTrue(result["partial"])
        for private_value in ("privateExtra", "must-not-appear", "unknownRoot", "also-private"):
            self.assertNotIn(private_value, repr(result))

    def test_wrong_shape_and_oversized_list_fail_closed(self):
        for result in (None, [], {"supportModels": None},
                       {"supportModels": [{"id": index, "name": "m"}
                                          for index in range(101)]}):
            with self.subTest(result_type=type(result).__name__):
                with self.assertRaises(SiteGatewaySupportedModelReferencesError):
                    project_site_gateway_supported_model_references(result)

    def test_exact_site_bound_get_and_controller_errors(self):
        client = self.client()
        site_ref = "a" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "supportModels": [{"id": 12, "name": "Model A", "private": "secret"}]}}) as request:
            result = client.read_site_gateway_supported_model_references(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-safe/internet/models", token="test-token")
        self.assertEqual(result["data"]["model_references"],
                         [{"model_id": 12, "model_name": "Model A"}])
        self.assertTrue(result["partial"])
        self.assertNotIn("secret", repr(result))
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", side_effect=OpenApiError("openapi_error_-44112")):
            with self.assertRaisesRegex(OpenApiError, "openapi_error_-44112"):
                client.read_site_gateway_supported_model_references(site_ref)

    def test_invalid_site_stops_and_route_guard_is_fixed(self):
        client = self.client()
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_gateway_supported_model_references("a" * 24)
            request.assert_not_called()
        self.assertTrue(client._site_gateway_supported_model_references_request_valid(
            "/openapi/v1/ctrl/sites/site-safe/internet/models"))
        self.assertFalse(client._site_gateway_supported_model_references_request_valid(
            "/openapi/v1/other/sites/site-safe/internet/models"))
        for path in ("/openapi/v1/ctrl/sites/site-safe/internet/models?x=1",
                     "/openapi/v1/ctrl/sites/site-safe/internet/models/extra"):
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET", path)

    def test_registry_maps_only_the_read_route(self):
        op = REGISTRY.get("site_gateway_supported_model_references")
        self.assertEqual(op.public_template,
                         "/v1/sites/{site_ref}/gateway-supported-model-references")
        self.assertEqual(op.upstream_template,
                         "/openapi/v1/{controller_id}/sites/{site_id}/internet/models")
        route, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{'a' * 24}/gateway-supported-model-references")
        self.assertEqual(route.operation_id, "site_gateway_supported_model_references")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24})
        for method, path in (
                ("POST", f"/v1/sites/{'a' * 24}/gateway-supported-model-references"),
                ("GET", f"/v1/sites/{'a' * 24}/gateway-supported-model-references-extra")):
            with self.assertRaises(RegistryError):
                REGISTRY.match(method, path)

    def test_runtime_capability_is_registered_without_claiming_live_support(self):
        client = self.client()
        item = next(row for row in client.capabilities()["items"]
                    if row["operation"] == "site_gateway_supported_model_references")
        self.assertEqual(item["implementation_state"], "implemented")
        self.assertEqual(item["support_state"], "unknown")
        self.assertEqual(item["runtime_evidence_count"], 0)


if __name__ == "__main__":
    unittest.main()
