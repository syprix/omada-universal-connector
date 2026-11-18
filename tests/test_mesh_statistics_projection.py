from __future__ import annotations

import unittest

from app.mesh_statistics import (
    MAX_CANDIDATE_PARENTS,
    MeshStatisticsProjectionError,
    project_mesh_statistics,
)


class MeshStatisticsProjectionTests(unittest.TestCase):
    def test_projects_typed_values_and_discards_identifiers(self) -> None:
        secret_mac = "00:11:22:33:44:55"
        source = {
            "status": 71,
            "statusCategory": -3,  # No enum is specified by the schema.
            "wirelessLinked": True,
            "scanStatus": 2,
            "wirelessUplink": {
                "uplinkMac": secret_mac, "name": "private AP", "ip": "192.0.2.7",
                "channel": 44, "rssi": -61, "snr": 30,
                "txRate": "private vendor string", "txRateInt": 866,
                "rxRateInt": 780, "upBytes": 1000, "downBytes": 2000,
                "upPackets": 10, "downPackets": 20, "activity": 50,
                "supportSpeedTest": False, "modelVersion": "private-version",
            },
            "childAps": [{"mac": secret_mac, "name": "private child", "ip": "192.0.2.8",
                          "rssi": -70, "supportSpeedTest": True,
                          "deviceSeriesType": 1, "model": "private-model"}],
            "candidateParents": [{
                "mac": secret_mac, "name": "private candidate", "linkStatus": 3,
                "hop": 2, "childsnum": 4, "priorityStatus": -1,
                "support5gMultiBand": True, "modelVersion": "private-version",
                "multiBandInfo": [{"radioId": 2, "channel": 149, "rssi": -67}],
            }],
        }

        projected = project_mesh_statistics(source)

        self.assertEqual(projected["status_category"], -3)
        self.assertEqual(projected["scan_status"], 2)
        self.assertEqual(projected["wireless_uplink"]["tx_rate_mbps"], 866)
        self.assertEqual(projected["wireless_uplink"]["rssi"], -61)
        self.assertEqual(projected["candidate_parents"][0]["link_status"], 3)
        self.assertEqual(projected["candidate_parents"][0]["multi_band_info"],
                         [{"radio_id": 2, "channel": 149, "rssi": -67,
                           "omitted_field_count": 0}])
        self.assertTrue(projected["partial"])
        rendered = str(projected)
        for private in (secret_mac, "private AP", "192.0.2.7", "private child",
                        "private candidate", "private-version", "private-model",
                        "private vendor string"):
            self.assertNotIn(private, rendered)

    def test_reports_bounded_array_truncation(self) -> None:
        result = project_mesh_statistics({
            "candidateParents": [{"linkStatus": 2}] * (MAX_CANDIDATE_PARENTS + 2)
        })
        self.assertEqual(len(result["candidate_parents"]), MAX_CANDIDATE_PARENTS)
        self.assertEqual(result["candidate_parents_count"], MAX_CANDIDATE_PARENTS + 2)
        self.assertEqual(result["omitted_candidate_parents_count"], 2)
        self.assertTrue(result["partial"])

    def test_reports_nested_omissions_as_partial(self) -> None:
        projected = project_mesh_statistics({"wirelessUplink": {"name": "private"}})
        self.assertEqual(projected["wireless_uplink"]["omitted_field_count"], 1)
        self.assertTrue(projected["partial"])

    def test_rejects_invalid_shapes_types_and_documented_enum_ranges(self) -> None:
        invalid = (
            None,
            {"wirelessLinked": 1},
            {"scanStatus": 4},
            {"wirelessUplink": {"txRateInt": True}},
            {"childAps": {}},
            {"candidateParents": [None]},
            {"candidateParents": [{"linkStatus": 5}]},
            {"wirelessUplink": {"upBytes": -1}},
        )
        for response in invalid:
            with self.subTest(response=response), self.assertRaises(MeshStatisticsProjectionError):
                project_mesh_statistics(response)


if __name__ == "__main__":
    unittest.main()
