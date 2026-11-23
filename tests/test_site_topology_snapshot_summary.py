import unittest

from app.site_topology_snapshot_summary import (
    TopologySnapshotError, summarize_topology_snapshot,
)


class TopologySnapshotSummaryTests(unittest.TestCase):
    def test_counts_nodes_edges_blocking_and_missing_refs_without_identity(self):
        result = summarize_topology_snapshot({
            "topologyNodes": [{"mac": "aa"}, {"mac": "bb"}, {"name": "hidden"}],
            "topologyEdges": [
                {"upLinkMac": "aa", "downLinkMac": "bb", "blocked": True,
                 "blockedVlans": "secret", "port": {"name": "private"}},
                {"upLinkMac": "aa", "downLinkMac": "missing", "blocked": False},
                {"upLinkMac": "aa", "blocked": None},
            ],
        })
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["node_count"], 3)
        self.assertEqual(result["edge_count"], 3)
        self.assertEqual(result["node_rows_without_reference_count"], 1)
        self.assertEqual(result["blocked_edge_count"], 1)
        self.assertEqual(result["unblocked_edge_count"], 1)
        self.assertEqual(result["edges_without_block_state_count"], 1)
        self.assertEqual(result["missing_endpoint_reference_count"], 1)
        self.assertEqual(result["unreported_endpoint_reference_count"], 1)
        self.assertNotIn("aa", repr(result))
        self.assertNotIn("secret", repr(result))

    def test_rejects_unbounded_or_invalid_snapshot(self):
        with self.assertRaises(TopologySnapshotError):
            summarize_topology_snapshot({"topologyNodes": [], "topologyEdges": [{}]},
                                        max_edges=0)
        with self.assertRaises(TopologySnapshotError):
            summarize_topology_snapshot({"topologyNodes": {}, "topologyEdges": []})
        with self.assertRaises(TopologySnapshotError):
            summarize_topology_snapshot({"topologyNodes": [],
                                         "topologyEdges": [{"blocked": 1}]})


if __name__ == "__main__":
    unittest.main()
