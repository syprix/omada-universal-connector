import unittest

from app.msp_customer_roles import MspCustomerRolesError, project_msp_customer_roles


class MspCustomerRolesTests(unittest.TestCase):
    def test_projects_only_aggregate_role_facts(self):
        result = project_msp_customer_roles([
            {"id": "private-role-id", "name": "private-role-name", "type": 1,
             "defaultRole": True, "source": 2, "privilege": {"secret-permission": True}},
            {"id": "another-id", "name": "another-name", "type": 0,
             "defaultRole": False, "source": 0},
        ])
        self.assertEqual(result["data"]["role_count"], 2)
        self.assertEqual(result["data"]["role_types"],
                         {"standard": 1, "customer": 1, "msp": 0})
        self.assertEqual(result["data"]["default_role_count"], 1)
        self.assertEqual(result["data"]["privilege_defined_role_count"], 1)
        for private in ("private-role-id", "private-role-name", "secret-permission"):
            self.assertNotIn(private, str(result))
        self.assertFalse(result["partial"])

    def test_marks_invalid_metadata_and_rejects_oversized_lists(self):
        result = project_msp_customer_roles([{"name": "private", "type": 9}])
        self.assertGreater(result["data"]["invalid_count"], 0)
        self.assertTrue(result["partial"])
        with self.assertRaises(MspCustomerRolesError):
            project_msp_customer_roles([{} for _ in range(1_001)])
