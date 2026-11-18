from __future__ import annotations

import unittest

from app.lldp_neighbors import (
    LldpNeighborProjectionError,
    MAX_NEIGHBOR_ROWS,
    project_lldp_neighbor_rows,
)


class LldpNeighborProjectionTests(unittest.TestCase):
    def test_projects_only_switch_port_presence_and_neighbor_counts(self) -> None:
        private_mac = "00:11:22:33:44:55"
        private_name = "uplink-to-private-device"
        rows = [
            {"portId": 8, "standardPort": "Port 8", "deviceId": "raw-id",
             "systemName": private_name, "neighborPortId": private_mac,
             "ttl": 120, "capabilities": "bridge"},
            {"portId": 3, "standardPort": "Port 3", "deviceId": "another-id",
             "systemName": "secret", "neighborPortId": "eth0", "ttl": 15},
            {"portId": 8, "systemName": private_name, "neighborPortId": private_mac},
        ]
        result = project_lldp_neighbor_rows(rows)

        self.assertEqual(result["scope"], "ports_with_returned_lldp_neighbors_only")
        self.assertEqual(result["ports"], [
            {"port_id": 3, "neighbor_present": True, "neighbor_count": 1},
            {"port_id": 8, "neighbor_present": True, "neighbor_count": 2},
        ])
        self.assertEqual(result["neighbor_entry_count"], 3)
        self.assertEqual(result["port_count"], 2)
        self.assertEqual(result["omitted_field_count"], 13)
        self.assertFalse(result["partial"])
        rendered = str(result)
        for secret in (private_mac, private_name, "raw-id", "eth0", "capabilities", "ttl"):
            self.assertNotIn(secret, rendered)

    def test_empty_rows_do_not_claim_anything_about_absent_ports(self) -> None:
        result = project_lldp_neighbor_rows([])
        self.assertEqual(result["ports"], [])
        self.assertEqual(result["port_count"], 0)
        self.assertEqual(result["neighbor_entry_count"], 0)
        self.assertEqual(result["scope"], "ports_with_returned_lldp_neighbors_only")
        self.assertFalse(result["partial"])

    def test_bounds_rows_and_reports_omitted_count(self) -> None:
        result = project_lldp_neighbor_rows(
            [{"portId": index % 10} for index in range(MAX_NEIGHBOR_ROWS + 4)])
        self.assertEqual(result["projected_neighbor_entry_count"], MAX_NEIGHBOR_ROWS)
        self.assertEqual(result["neighbor_entry_count"], MAX_NEIGHBOR_ROWS + 4)
        self.assertEqual(result["omitted_neighbor_entry_count"], 4)
        self.assertTrue(result["partial"])
        self.assertEqual(result["port_count"], 10)

    def test_rejects_bad_shapes_and_port_values(self) -> None:
        for rows in (None, {}, [None], [{"systemName": "private"}],
                     [{"portId": True}], [{"portId": -1}], [{"portId": 4097}],
                     [{"portId": "3"}], [{"portId": 1.0}]):
            with self.subTest(rows=rows), self.assertRaises(LldpNeighborProjectionError):
                project_lldp_neighbor_rows(rows)


if __name__ == "__main__":
    unittest.main()
