import unittest

from app.controller_ui_interface import (
    BOOL_FIELD, INT_FIELDS, REDACTED_STRING_FIELDS, ControllerUiInterfaceError,
    project_controller_ui_interface,
)


class ControllerUiInterfaceTests(unittest.TestCase):
    def test_each_documented_integer_field(self):
        for source, (target, low, high) in INT_FIELDS.items():
            value = 0 if low is None else low
            with self.subTest(source=source):
                result = project_controller_ui_interface({source: value})
                self.assertEqual(result["data"]["settings"], {target: value})
                self.assertTrue(result["partial"])

    def test_boolean_and_redacted_string_fields(self):
        for value in (False, True):
            with self.subTest(enable=value):
                self.assertEqual(project_controller_ui_interface({BOOL_FIELD: value})["data"]["settings"],
                                 {"private_labeling_enabled": value})
        for source in REDACTED_STRING_FIELDS:
            with self.subTest(field=source):
                result = project_controller_ui_interface({source: "private value"})
                self.assertEqual(result["data"]["redacted_field_count"], 1)
                self.assertNotIn("private value", str(result))

    def test_complete_projection_and_unknown_fields(self):
        raw = {"timeZone": 0, "refreshRate": 4, "macFormat": 99,
               "privateLabelingEnable": True, "privateLabelingUrl": "https://example.invalid/x",
               "privateLabelingFileId": "secret-id", "privateLabelingFileName": "brand.png"}
        result = project_controller_ui_interface(raw)
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["present_count"], 4)
        self.assertEqual(result["data"]["redacted_field_count"], 3)
        for value in raw.values():
            if isinstance(value, str):
                self.assertNotIn(value, str(result))
        extra = project_controller_ui_interface({"timeZone": 1, "extra": "hide"})
        self.assertEqual(extra["data"]["unknown_field_count"], 1)
        self.assertNotIn("extra", str(extra))

    def test_malformed_values_and_bounds(self):
        for field, value in (("timeZone", 4), ("refreshRate", 5), ("macFormat", True),
                             (BOOL_FIELD, 1), ("privateLabelingUrl", 4)):
            with self.subTest(field=field):
                result = project_controller_ui_interface({field: value})
                self.assertEqual(result["data"]["invalid_count"], 1)
        for value in (None, [], "bad", {str(i): i for i in range(17)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(ControllerUiInterfaceError):
                project_controller_ui_interface(value)


if __name__ == "__main__":
    unittest.main()
