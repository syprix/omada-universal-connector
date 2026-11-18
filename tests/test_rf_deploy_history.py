from __future__ import annotations

import unittest

from app.rf_deploy_history import RfDeployHistoryError, project_rf_deploy_history


class RfDeployHistoryTests(unittest.TestCase):
    def test_projects_boolean_and_preserves_its_documented_meaning(self) -> None:
        result = project_rf_deploy_history({"firstDeploy": True})
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"], {"first_deployment": True})
        self.assertEqual(project_rf_deploy_history({"firstDeploy": False})["data"],
                         {"first_deployment": False})

    def test_missing_invalid_and_unknown_values_are_partial(self) -> None:
        self.assertIn("firstDeploy", project_rf_deploy_history({})["missing_fields"])
        invalid = project_rf_deploy_history({"firstDeploy": 1})
        self.assertTrue(invalid["partial"])
        self.assertEqual(invalid["omitted_field_count"], 1)
        unknown = project_rf_deploy_history({"firstDeploy": True, "private": "secret"})
        self.assertTrue(unknown["partial"])
        self.assertNotIn("secret", repr(unknown))

    def test_invalid_root_and_excess_fields_fail_closed(self) -> None:
        for raw in (None, [], {f"x{i}": i for i in range(9)}):
            with self.subTest(raw=raw), self.assertRaises(RfDeployHistoryError):
                project_rf_deploy_history(raw)


if __name__ == "__main__":
    unittest.main()
