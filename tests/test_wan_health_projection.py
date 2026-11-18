from __future__ import annotations

import math
import unittest

from app.wan_health import MAX_WAN_PORTS, WanHealthProjectionError, project_wan_details


class WanHealthProjectionTests(unittest.TestCase):
    def test_projects_documented_numeric_values_and_redacts_identity(self) -> None:
        private_values = ("private WAN", "198.51.100.9", "00:11:22:33:44:55")
        projected = project_wan_details({"wanDetails": [{
            "name": private_values[0], "ip": private_values[1], "gatewayMac": private_values[2],
            "port": 2, "proto": 7, "speed": 1000, "duplex": 1,
            "rx": 1234, "tx": 5678, "rxRate": 90, "txRate": 100,
            "latency": 18, "loss": 0.25,
        }]})
        self.assertEqual(projected["count"], 1)
        self.assertTrue(projected["partial"])
        port = projected["wan_details"][0]
        self.assertEqual(port["port"], 2)
        self.assertEqual(port["protocol_code"], 7)
        self.assertEqual(port["speed_code"], 1000)
        self.assertEqual(port["duplex_code"], 1)
        self.assertEqual(port["rx_rate"], 90)
        self.assertEqual(port["loss"], 0.25)
        self.assertEqual(port["omitted_field_count"], 3)
        rendered = str(projected)
        for private in private_values:
            self.assertNotIn(private, rendered)

    def test_reports_missing_list_and_bounded_truncation(self) -> None:
        missing = project_wan_details({})
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["missing_fields"], ["wanDetails"])

        projected = project_wan_details({"wanDetails": [{"port": i} for i in range(MAX_WAN_PORTS + 3)]})
        self.assertEqual(len(projected["wan_details"]), MAX_WAN_PORTS)
        self.assertEqual(projected["count"], MAX_WAN_PORTS + 3)
        self.assertEqual(projected["omitted_wan_detail_count"], 3)
        self.assertTrue(projected["partial"])

    def test_projects_direct_hardware_controller_list_response(self) -> None:
        projected = project_wan_details([{
            "port": 1, "proto": 2, "speed": 1000, "duplex": 1,
            "rx": 10, "tx": 20, "rxRate": 3, "txRate": 4,
            "latency": 5, "loss": 0.1, "name": "private label",
            "ip": "192.0.2.10",
        }])
        self.assertEqual(projected["count"], 1)
        self.assertEqual(projected["wan_details"][0]["port"], 1)
        self.assertTrue(projected["partial"])
        self.assertNotIn("private label", repr(projected))
        self.assertNotIn("192.0.2.10", repr(projected))

    def test_rejects_bad_numeric_shapes_and_bounds(self) -> None:
        invalid_rows = (
            None, {"port": True}, {"port": 2**31}, {"rx": 2**63},
            {"txRate": "100"}, {"latency": 1.2}, {"loss": True},
            {"loss": math.inf}, {"loss": math.nan}, {"loss": 10**400},
        )
        for row in invalid_rows:
            with self.subTest(row=row), self.assertRaises(WanHealthProjectionError):
                project_wan_details({"wanDetails": [row]})
        with self.assertRaises(WanHealthProjectionError):
            project_wan_details({"wanDetails": {"port": 1}})
        with self.assertRaises(WanHealthProjectionError):
            project_wan_details(None)


if __name__ == "__main__":
    unittest.main()
