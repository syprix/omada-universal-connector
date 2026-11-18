import unittest

from app.controller_client_recognition import (
    ControllerClientRecognitionError, project_controller_client_recognition,
)


class ControllerClientRecognitionTests(unittest.TestCase):
    def test_maps_documented_boolean(self):
        for value in (False, True):
            with self.subTest(value=value):
                self.assertEqual(project_controller_client_recognition({"enable": value}), {
                    "data": {"enabled": value, "present_count": 1, "missing_count": 0,
                             "invalid_count": 0, "unknown_field_count": 0},
                    "partial": False,
                })

    def test_missing_invalid_and_unknown_fields_are_separate(self):
        missing = project_controller_client_recognition({})
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["data"]["missing_count"], 1)
        for value in (0, 1, "true", None):
            with self.subTest(value=value):
                result = project_controller_client_recognition({"enable": value})
                self.assertIsNone(result["data"]["enabled"])
                self.assertEqual(result["data"]["invalid_count"], 1)
                self.assertTrue(result["partial"])
        unknown = project_controller_client_recognition({"enable": True, "private": "hidden"})
        self.assertEqual(unknown["data"]["unknown_field_count"], 1)
        self.assertTrue(unknown["partial"])
        self.assertNotIn("private", str(unknown))

    def test_rejects_wrong_response_shapes_and_bounds_fields(self):
        for result in (None, [], "true", {str(i): i for i in range(17)}):
            with self.subTest(value=type(result).__name__), self.assertRaises(ControllerClientRecognitionError):
                project_controller_client_recognition(result)


if __name__ == "__main__":
    unittest.main()
