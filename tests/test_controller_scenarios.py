import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.scenario_difference_summary import summarize_scenario_differences


class ControllerScenariosTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller_1", "client-id-file",
            "client-secret-file", cert_sha256="a" * 64))

    def test_reads_documented_string_list_and_bounds_output(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": ["Wireless", "Switching", "Routing"]}) as request:
            result = self.client.read_controller_scenarios()
        self.assertEqual(request.call_args.args[:2],
                         ("GET", "/openapi/v1/controller_1/scenarios"))
        self.assertEqual(result, {
            "status": "ok", "resource": "controller_scenarios",
            "scenario_count": 3, "items": ["Wireless", "Switching", "Routing"],
            "partial": False,
        })

    def test_invalid_entries_and_large_lists_are_partial(self):
        values = ["Scenario"] * 100 + ["extra"]
        values[5] = "has\ncontrol"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": values}):
            result = self.client.read_controller_scenarios()
        self.assertEqual(result["scenario_count"], 101)
        self.assertEqual(len(result["items"]), 99)
        self.assertTrue(result["partial"])
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_scenarios()

    def test_scenario_differences_are_projected_from_documented_fields(self):
        payload = {"result": [
            {"name": "Default", "isDefault": True, "secret": "omit"},
            {"name": "Changed", "isDefault": False, "id": "omit"},
        ]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_controller_scenario_differences()
        self.assertEqual(request.call_args.args[:2], (
            "GET", "/openapi/v1/controller_1/scenarios/difference"))
        self.assertEqual(result["items"], [
            {"name": "Default", "is_default": True},
            {"name": "Changed", "is_default": False},
        ])
        self.assertEqual(result["default_count"], 1)
        self.assertNotIn("secret", repr(result))
        partial = summarize_scenario_differences([
            {"name": "Default", "isDefault": True},
            {"name": "bad\nname", "isDefault": False},
        ])
        self.assertTrue(partial["partial"])
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_scenario_differences()


if __name__ == "__main__":
    unittest.main()
