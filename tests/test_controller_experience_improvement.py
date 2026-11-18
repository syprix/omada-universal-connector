import unittest

from app.controller_experience_improvement import project_controller_experience_improvement


class ControllerExperienceImprovementTests(unittest.TestCase):
    def test_projects_strict_boolean(self):
        self.assertEqual(project_controller_experience_improvement({"expImprove": True}), {
            "data": {"experience_improvement_enabled": True, "present_count": 1,
                     "missing_count": 0, "invalid_count": 0, "unknown_field_count": 0},
            "partial": False,
        })
        self.assertFalse(project_controller_experience_improvement({"expImprove": False})[
            "data"]["experience_improvement_enabled"])

    def test_malformed_and_unknown_values_are_not_returned(self):
        result = project_controller_experience_improvement(
            {"expImprove": 1, "extra": "private"})
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertIsNone(result["data"]["experience_improvement_enabled"])
        self.assertNotIn("private", str(result))
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
