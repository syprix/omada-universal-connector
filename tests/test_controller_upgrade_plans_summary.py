import unittest

from app.controller_upgrade_plans_summary import (
    ControllerUpgradePlansError, project_controller_upgrade_plans,
)


class ControllerUpgradePlansSummaryTests(unittest.TestCase):
    def test_counts_documented_plan_fields_and_redacts_values(self):
        result = project_controller_upgrade_plans([{
            "id": "secret-id", "modelTypeInfo": {"showModel": "Secret Model",
                                                   "compoundModel": "Private Model"},
            "siteNames": ["Secret Site"], "siteNum": 2,
            "currentVersion": ["1.0", "1.1"], "targetVersion": "2.0",
            "scheduledUpgradeTime": "2026-01-01T00:00:00Z", "operator": "secret-user",
            "fromRollback": False,
        }], 1, 1, 10)
        self.assertEqual(result["plan_count"], 1)
        self.assertEqual(result["current_version_entry_count"], 2)
        self.assertEqual(result["site_association_count"], 2)
        self.assertEqual(result["rollback_origin_counts"],
                         {"true": 0, "false": 1, "unknown": 0})
        for secret in ("secret-id", "Secret Model", "Private Model", "Secret Site",
                       "1.0", "2.0", "2026-01-01", "secret-user"):
            self.assertNotIn(secret, str(result))
        self.assertFalse(result["scheduled_time_interpreted"])
        self.assertFalse(result["execution_started_or_completed_inferred"])
        self.assertFalse(result["partial"])

    def test_missing_plan_fields_mark_partial(self):
        result = project_controller_upgrade_plans([{}], 1, 1, 10)
        self.assertTrue(result["partial"])
        self.assertEqual(result["rollback_origin_counts"]["unknown"], 1)

    def test_rejects_invalid_lists_counts_and_rollback_types(self):
        for rows in ([{"siteNum": True}], [{"siteNames": [1]}],
                     [{"fromRollback": 1}], [None]):
            with self.subTest(rows=rows), self.assertRaises(ControllerUpgradePlansError):
                project_controller_upgrade_plans(rows, 1, 1, 1)


if __name__ == "__main__":
    unittest.main()
