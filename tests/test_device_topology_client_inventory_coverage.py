import unittest

from app.device_topology_client_inventory_coverage import (
    DeviceTopologyClientInventoryError,
    project_device_topology_client_inventory_coverage,
)


class DeviceTopologyClientInventoryCoverageTests(unittest.TestCase):
    def test_empty_list_is_complete_empty_coverage(self):
        result = project_device_topology_client_inventory_coverage([])
        self.assertEqual(result["topology_client_count"], 0)
        self.assertFalse(result["partial"])
        self.assertFalse(result["client_identities_returned"])

    def test_sparse_valid_row_counts_missing_optional_fields_without_partial(self):
        result = project_device_topology_client_inventory_coverage([{"wireless": True}])
        self.assertEqual(result["topology_client_count"], 1)
        self.assertEqual(result["client_field_coverage"]["type"]["missing"], 1)
        self.assertEqual(result["client_field_coverage"]["ip"]["missing"], 1)
        self.assertFalse(result["partial"])

    def test_rows_return_only_field_counts_and_discard_identity(self):
        rows = [{"mac": "private-client", "name": "private name", "ip": "192.0.2.3",
                 "wireless": True, "guest": False, "type": "phone", "vendor": "Acme-Lab",
                 "model": "Model-Z", "devTxRate": 0, "devRxRate": 1, "healthScore": 2,
                 "wiredUpInfo": {}, "wirelessUpInfo": {}, "connectedNetwork": {},
                 "connectedSsid": {}}]
        result = project_device_topology_client_inventory_coverage(rows)
        self.assertEqual(result["topology_client_count"], 1)
        self.assertEqual(result["client_field_coverage"]["wireless"]["type_valid"], 1)
        self.assertFalse(result["partial"])
        self.assertNotIn("private-client", repr(result))
        self.assertNotIn("private name", repr(result))
        self.assertNotIn("192.0.2.3", repr(result))
        self.assertNotIn("Acme-Lab", repr(result))
        self.assertNotIn("Model-Z", repr(result))

    def test_unknown_and_invalid_fields_are_counted_without_names_or_values(self):
        result = project_device_topology_client_inventory_coverage([
            {"wireless": "invalid", "type": "phone", "privateKey": "private-value"}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["client_field_coverage"]["wireless"]["invalid"], 1)
        self.assertNotIn("privateKey", repr(result))
        self.assertNotIn("private-value", repr(result))

    def test_row_limit_is_enforced(self):
        with self.assertRaises(DeviceTopologyClientInventoryError):
            project_device_topology_client_inventory_coverage([{}] * 4097)


if __name__ == "__main__":
    unittest.main()
