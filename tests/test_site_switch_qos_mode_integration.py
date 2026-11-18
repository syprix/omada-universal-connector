import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SiteSwitchQosModeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_reads_fixed_route_and_returns_documented_mode(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"qosMode": 1, "completed": 0}}) as request:
            result = self.client.read_site_switch_qos_mode(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/switch-qos/qos-mode", token="token")
        self.assertEqual(result["data"], {
            "mode": "rules_based", "transition_completed": False,
        })

    def test_rejects_other_controller_and_invalid_response(self):
        good = "/openapi/v1/ctrl/sites/site_1/switch-qos/qos-mode"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": None}), \
                self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
            self.client.read_site_switch_qos_mode(self.site_ref)
        for value, expected_invalid, expected_missing in (
                ({}, 0, 2), ({"qosMode": 2, "completed": 1}, 1, 0)):
            with self.subTest(value=value), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": value}):
                result = self.client.read_site_switch_qos_mode(self.site_ref)
                self.assertEqual(result["invalid_field_count"], expected_invalid)
                self.assertEqual(result["missing_field_count"], expected_missing)

    def test_reads_fixed_scheduler_and_dscp_mapping_routes(self):
        fixtures = (
            ("read_site_switch_qos_scheduler_summary",
             "/openapi/v1/ctrl/sites/site_1/switch-qos/qos-rule/scheduler-mapping",
             {"id": "private-id", "name": "private-name", "types": 1,
              "buildIn": True, "mapping": [{"queue": 1, "type": 0}]},
             "site_switch_qos_scheduler_summary"),
            ("read_site_switch_qos_dscp_summary",
             "/openapi/v1/ctrl/sites/site_1/switch-qos/qos-rule/dscp-mapping",
             {"mapping": {"queue-0": list(range(8))}},
             "site_switch_qos_dscp_summary"),
        )
        for method, path, payload, resource in fixtures:
            with self.subTest(resource=resource), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": payload}) as request:
                result = getattr(self.client, method)(self.site_ref)
            request.assert_called_once_with("GET", path, token="token")
            self.assertEqual(result["resource"], resource)
            self.assertNotIn("private", repr(result))


if __name__ == "__main__":
    unittest.main()
