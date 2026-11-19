from __future__ import annotations

import unittest

from app.site_stack_connections_summary import summarize_site_stack_connections


STACK_REF = "c" * 24
SWITCH_REF = "a" * 24
MAC = "aa:bb:cc:dd:ee:ff"


class SiteStackConnectionsSummaryTests(unittest.TestCase):
    def test_maps_documented_members_and_aggregates_lldp_without_neighbor_identity(self) -> None:
        result = summarize_site_stack_connections(
            [{"id": "private-stack-id", "name": "private-stack-name", "status": 0,
              "member": [{"mac": MAC, "name": "private-member-name"}]}],
            {SWITCH_REF: MAC}, lambda _raw_id: STACK_REF,
            {STACK_REF: [{"portId": 3, "deviceId": "neighbor-secret",
                          "systemName": "neighbor-name", "neighborPortId": "remote-port",
                          "ttl": 120, "capabilities": "bridge"}]})
        stack = result["data"]["stacks"][0]
        self.assertEqual(stack["member_switch_refs"], [SWITCH_REF])
        self.assertEqual(stack["status_code"], 0)
        self.assertEqual(stack["lldp_port_neighbors"], [
            {"port_id": 3, "neighbor_present": True, "neighbor_count": 1}])
        self.assertEqual(stack["unresolved_neighbor_identity_count"], 1)
        self.assertEqual(result["status"], "ok")
        rendered = repr(result)
        for private in ("private-stack-id", "private-stack-name", MAC,
                        "neighbor-secret", "neighbor-name", "remote-port"):
            self.assertNotIn(private, rendered)

    def test_ambiguous_members_and_truncated_neighbor_page_remain_partial(self) -> None:
        second_ref = "b" * 24
        result = summarize_site_stack_connections(
            [{"id": "stack", "status": 1,
              "member": [{"mac": MAC}, {"mac": "00:00:00:00:00:02"}]}],
            {SWITCH_REF: MAC, second_ref: MAC}, lambda _raw_id: STACK_REF,
            {STACK_REF: [{"portId": 1}]},
            neighbor_omitted_by_stack_ref={STACK_REF: 4})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["ambiguous_stack_members"], 1)
        stack = result["data"]["stacks"][0]
        self.assertEqual(stack["omitted_neighbor_entry_count"], 4)
        self.assertEqual(stack["mapped_member_count"], 0)

    def test_stack_limit_is_visible(self) -> None:
        rows = [{"id": f"stack-{index}", "status": 0, "member": []}
                for index in range(33)]
        result = summarize_site_stack_connections(
            rows, {}, lambda raw_id: raw_id.encode().hex()[:24],
            {row["id"].encode().hex()[:24]: [] for row in rows})
        self.assertTrue(result["partial"])
        self.assertEqual(result["stack_count"], 32)
        self.assertEqual(result["stacks_omitted_device_limit"], 1)


if __name__ == "__main__":
    unittest.main()
