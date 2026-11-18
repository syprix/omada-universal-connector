import unittest

from app.switch_qos_mapping import (
    SwitchQosMappingError, project_dscp_mapping, project_scheduler_mapping,
)


class SwitchQosMappingTests(unittest.TestCase):
    def test_scheduler_mapping_returns_presence_and_counts_only(self):
        result = project_scheduler_mapping({
            "id": "private-id", "name": "private-name", "types": 3,
            "buildIn": True,
            "mapping": [{"queue": 0, "type": 1, "weight": 8},
                        {"queue": 1, "type": 2}],
        })
        self.assertEqual(result["data"], {
            "id_present": True, "name_present": True, "type_configured": True,
            "built_in": True, "mapping_count": 2, "rows_with_valid_fields": 2,
            "queue_value_count": 2, "scheduler_type_value_count": 2,
            "weight_value_count": 1,
        })
        self.assertNotIn("private", repr(result))

    def test_scheduler_mapping_counts_malformed_fields(self):
        result = project_scheduler_mapping({
            "types": True, "mapping": [{"queue": 1, "type": "private"}],
            "future": "private",
        })
        self.assertGreater(result["invalid_field_count"], 0)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_dscp_mapping_returns_only_queue_and_value_counts(self):
        result = project_dscp_mapping({"mapping": {
            "queue-0": list(range(8)), "queue-1": list(range(8, 16)),
        }})
        self.assertEqual(result["data"], {"queue_count": 2, "mapped_value_count": 16})
        self.assertNotIn("queue-0", repr(result))
        self.assertNotIn("15", repr(result))

    def test_dscp_mapping_validates_bounds_and_fixed_list_size(self):
        result = project_dscp_mapping({"mapping": {"queue": [1, 2]}})
        self.assertEqual(result["invalid_field_count"], 1)
        with self.assertRaises(SwitchQosMappingError):
            project_dscp_mapping({"mapping": {str(i): [0] * 8 for i in range(33)}})
        self.assertEqual(project_scheduler_mapping({"mapping": [{}] * 65})[
            "invalid_field_count"], 1)


if __name__ == "__main__":
    unittest.main()
