import unittest
from unittest.mock import patch
from app.openapi import OmadaOpenApiClient, OpenApiConfig

from app.controller_upgrade_model_list_summary import (
    ControllerUpgradeModelListError, summarize_upgrade_models,
)


class ControllerUpgradeModelListSummaryTests(unittest.TestCase):
    def test_counts_documented_types_and_statuses_without_model_values(self):
        result = summarize_upgrade_models([
            {"modelTypeInfo": {"showModel": "ER605", "compoundModel": "secret"},
             "currentVersion": ["1.2.3"], "status": 0, "upgradeStatus": 1},
            {"modelTypeInfo": {"showModel": "EAP", "compoundModel": "secret2"},
             "currentVersion": [], "status": 1, "upgradeStatus": 0},
        ], 2, 1, 10)
        self.assertEqual(result["critical_status_counts"],
                         {"good": 1, "critical": 1, "unknown": 0})
        self.assertEqual(result["upgrade_status_counts"],
                         {"up_to_date": 1, "new_version_available": 1, "unknown": 0})
        self.assertEqual(result["model_type_info_reported_count"], 2)
        self.assertNotIn("ER605", str(result))
        self.assertNotIn("1.2.3", str(result))

    def test_missing_values_and_truncation_are_partial(self):
        result = summarize_upgrade_models([{"currentVersion": []}], 2, 1, 1)
        self.assertTrue(result["partial"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["critical_status_counts"]["unknown"], 1)
        with self.assertRaises(ControllerUpgradeModelListError):
            summarize_upgrade_models({}, 0, 0, 1)

    def test_adapter_pages_only_the_documented_model_list(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=2, max_pages=2))
        pages = [
            {"result": {"totalRows": 3, "currentPage": 1, "currentSize": 2,
                        "data": [{"status": 0, "upgradeStatus": 1},
                                 {"status": 1, "upgradeStatus": 0}]}},
            {"result": {"totalRows": 3, "currentPage": 2, "currentSize": 1,
                        "data": [{"status": 0, "upgradeStatus": 0}]}},
        ]
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=pages) as request:
            result = client.read_controller_upgrade_model_list_summary()
        self.assertEqual([call.args[1] for call in request.call_args_list], [
            "/openapi/v1/ctrl/upgrade/plan/models?page=1&pageSize=2",
            "/openapi/v1/ctrl/upgrade/plan/models?page=2&pageSize=2",
        ])
        self.assertEqual(result["reported_model_count"], 3)
        self.assertFalse(result["partial"])
        self.assertTrue(client._controller_upgrade_model_list_request_valid(
            "/openapi/v1/ctrl/upgrade/plan/models?page=1&pageSize=100"))
        self.assertFalse(client._controller_upgrade_model_list_request_valid(
            "/openapi/v1/other/upgrade/plan/models?page=1&pageSize=100"))
        self.assertFalse(client._controller_upgrade_model_list_request_valid(
            "/openapi/v1/ctrl/upgrade/plan/models?page=11&pageSize=100"))


if __name__ == "__main__":
    unittest.main()
