from __future__ import annotations

import unittest

from app.switch_statistics import SwitchStatisticsError, summarize_switch_statistics


class SwitchStatisticsProjectionTests(unittest.TestCase):
    def test_returns_aggregate_health_and_port_counts_without_identifiers(self) -> None:
        result = summarize_switch_statistics({
            "name": "private-switch-name", "status": 14, "statusCategory": 1,
            "portNum": 2,
            "ports": [
                {"port": 1, "name": "private-port-name", "type": 1,
                 "portStatus": {"linkStatus": 1, "poe": True, "stpDiscarding": False,
                                "tx": 100, "rx": 50, "total": 150}},
                {"port": 2, "name": "another-private-port", "type": 3,
                 "portStatus": {"linkStatus": 0, "poe": False, "stpDiscarding": True,
                                "tx": 0, "rx": 0, "total": 0}},
            ],
            "uplink": {"port": 1, "mac": "00:11:22:33:44:55", "name": "private-uplink"},
            "supportPoe": True, "supportStack": False, "supportSTP": True,
            "speeds": [0, 3, 3],
            "mlagMsg": {"mlagId": "private-mlag-id", "mlagName": "private-mlag-name",
                        "role": 1, "dadLinkPort": [1], "peerLinkPort": [2]},
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["resource"], "switch_statistics")
        self.assertEqual(result["data"]["status_code"], 14)
        self.assertEqual(result["data"]["port_count"], 2)
        self.assertEqual(result["data"]["by_link_status_code"], {"0": 1, "1": 1})
        self.assertEqual(result["data"]["by_port_type_code"], {"1": 1, "3": 1})
        self.assertEqual(result["data"]["by_poe_in_use"], {"false": 1, "true": 1})
        self.assertEqual(result["data"]["tx_bytes"], 100)
        self.assertEqual(result["data"]["rx_bytes"], 50)
        self.assertEqual(result["data"]["total_bytes"], 150)
        self.assertEqual(result["data"]["supported_speed_codes"], [0, 3])
        self.assertEqual(result["data"]["dad_link_count"], 1)
        for secret in ("private-switch-name", "private-port-name", "another-private-port",
                       "00:11:22:33:44:55", "private-uplink", "private-mlag-id",
                       "private-mlag-name", '"port"', '"name"'):
            self.assertNotIn(secret, repr(result))

    def test_marks_invalid_codes_and_incomplete_port_rows_partial(self) -> None:
        result = summarize_switch_statistics({
            "status": True, "statusCategory": 9, "portNum": -1,
            "ports": [{"type": 99, "portStatus": {"linkStatus": True,
                       "poe": 1, "stpDiscarding": None, "tx": -1, "rx": 0, "total": 0}}],
            "supportPoe": "yes", "supportStack": False, "supportSTP": True,
            "speeds": [999], "uplink": "private",
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 6)
        self.assertEqual(result["data"]["unknown_port_rows"], 1)
        self.assertNotIn("private", repr(result))

    def test_rejects_oversized_response_or_port_list(self) -> None:
        with self.assertRaises(SwitchStatisticsError):
            summarize_switch_statistics({"ports": [{}] * 4097})
        with self.assertRaises(SwitchStatisticsError):
            summarize_switch_statistics({str(i): None for i in range(65)})


if __name__ == "__main__":
    unittest.main()
