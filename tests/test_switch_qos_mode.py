import unittest

from app.switch_qos_mode import SwitchQosModeError, project_switch_qos_mode


class SwitchQosModeTests(unittest.TestCase):
    def test_projects_documented_modes_without_raw_values(self):
        self.assertEqual(project_switch_qos_mode({"qosMode": 1, "completed": 0}), {
            "data": {"mode": "rules_based", "transition_completed": False},
            "missing_field_count": 0, "invalid_field_count": 0,
            "unknown_field_count": 0, "partial": False,
        })
        self.assertEqual(project_switch_qos_mode({"qosMode": 0, "completed": 1})[
            "data"], {"mode": "profile_based", "transition_completed": True})

    def test_counts_invalid_unknown_and_missing_fields_without_echoing_values(self):
        result = project_switch_qos_mode({"qosMode": 9, "completed": True,
                                          "private": "secret"})
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("secret", repr(result))
        self.assertTrue(result["partial"])
        self.assertEqual(project_switch_qos_mode({})["missing_field_count"], 2)

    def test_rejects_unbounded_objects(self):
        with self.assertRaises(SwitchQosModeError):
            project_switch_qos_mode({str(i): i for i in range(9)})


if __name__ == "__main__":
    unittest.main()
