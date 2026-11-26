import unittest

from app.site_gateway_qos_service_reference_inventory import (
    GatewayQosServiceReferenceInventoryError,
    project_gateway_qos_service_reference_inventory,
)


class GatewayQosServiceReferenceInventoryTests(unittest.TestCase):
    def test_explicit_empty_list_is_distinguished_and_not_claimed_complete(self):
        result = project_gateway_qos_service_reference_inventory({"data": []})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["row_count"], 0)
        self.assertTrue(result["empty"])
        self.assertFalse(result["partial"])
        self.assertFalse(result["server_completeness_established"])

    def test_counts_valid_unique_fields_without_returning_reference_values(self):
        result = project_gateway_qos_service_reference_inventory({"data": [
            {"id": "private-id-1", "name": "private-name-1"},
            {"id": "private-id-2", "name": "private-name-2"},
        ]})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["id_valid_count"], 2)
        self.assertEqual(result["id_unique_count"], 2)
        self.assertEqual(result["duplicate_reference_count"], 0)
        self.assertEqual(result["name_valid_count"], 2)
        self.assertNotIn("private-id", repr(result))
        self.assertNotIn("private-name", repr(result))

    def test_missing_invalid_duplicate_and_unknown_fields_are_counted(self):
        result = project_gateway_qos_service_reference_inventory({"data": [
            {"id": "duplicate", "name": "one", "extra": "must-not-appear"},
            {"id": "duplicate", "name": "two"},
            {"id": "", "name": 7},
            {"name": "missing-id"},
        ]})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["id_present_count"], 3)
        self.assertEqual(result["id_valid_count"], 2)
        self.assertEqual(result["id_invalid_count"], 1)
        self.assertEqual(result["id_missing_count"], 1)
        self.assertEqual(result["id_unique_count"], 1)
        self.assertEqual(result["duplicate_reference_count"], 1)
        self.assertEqual(result["name_present_count"], 4)
        self.assertEqual(result["name_valid_count"], 3)
        self.assertEqual(result["name_invalid_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        for value in ("one", "two", "missing-id", "must-not-appear"):
            self.assertNotIn(value, repr(result))

    def test_malformed_rows_and_unrecognized_shapes_remain_partial_or_fail_closed(self):
        result = project_gateway_qos_service_reference_inventory({"data": [
            None, {"id": "valid", "name": "name"}
        ]})
        self.assertEqual(result["invalid_row_count"], 1)
        self.assertEqual(result["id_valid_count"], 1)
        self.assertTrue(result["partial"])
        for value in (None, [], {"data": None}, {"items": []}):
            with self.subTest(value_shape=type(value).__name__), \
                    self.assertRaises(GatewayQosServiceReferenceInventoryError):
                project_gateway_qos_service_reference_inventory(value)
        many_fields = project_gateway_qos_service_reference_inventory({"data": [
            {"id": "x", **{f"extra{i}": i for i in range(16)}}]})
        self.assertEqual(many_fields["invalid_row_count"], 1)
        self.assertTrue(many_fields["partial"])
        long_id = project_gateway_qos_service_reference_inventory({"data": [
            {"id": "x" * 257}]})
        self.assertEqual(long_id["id_invalid_count"], 1)
        self.assertEqual(long_id["id_valid_count"], 0)
        self.assertTrue(long_id["partial"])


if __name__ == "__main__":
    unittest.main()
