import unittest

from app.switch_network_membership import (
    SwitchNetworkMembershipError,
    summarize_switch_network_membership,
)


class SwitchNetworkMembershipTests(unittest.TestCase):
    def test_projects_membership_counts_without_identifiers(self) -> None:
        result = summarize_switch_network_membership([{
            "id": "network-secret", "name": "private-name", "vlan": 30,
            "isolation": True,
            "portLagNetworkInfo": {
                "nativePorts": [1, 2], "nativeStPorts": ["1/0/1"], "nativeLags": [1],
                "tagPorts": [3], "tagStPorts": [], "tagLags": [2],
                "untagPorts": [], "untagStPorts": ["1/0/2"], "untagLags": [],
                "ipaddr": "192.0.2.1", "mode": 0, "vlan": 30,
            },
        }])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["summary"]["isolated_networks"], 1)
        self.assertEqual(result["summary"]["memberships"], {
            "native": {"ports": 3, "lags": 1},
            "tagged": {"ports": 1, "lags": 1},
            "untagged": {"ports": 1, "lags": 0},
        })
        self.assertNotIn("private-name", repr(result))
        self.assertNotIn("192.0.2.1", repr(result))
        self.assertFalse(result["partial"])

    def test_marks_malformed_fields_partial(self) -> None:
        result = summarize_switch_network_membership([{
            "isolation": "yes", "portLagNetworkInfo": {"nativePorts": [True]},
        }])
        self.assertTrue(result["partial"])
        self.assertEqual(result["summary"]["unknown_network_rows"], 1)
        self.assertEqual(result["summary"]["incomplete_membership_rows"], 1)

    def test_rejects_oversized_rows_and_membership_lists(self) -> None:
        with self.assertRaises(SwitchNetworkMembershipError):
            summarize_switch_network_membership([{}] * 10_001)
        with self.assertRaises(SwitchNetworkMembershipError):
            summarize_switch_network_membership([{
                "isolation": False,
                "portLagNetworkInfo": {"nativePorts": list(range(100_001))},
            }])


if __name__ == "__main__":
    unittest.main()
