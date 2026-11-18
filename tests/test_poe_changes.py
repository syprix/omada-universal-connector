from __future__ import annotations

import unittest

from app.poe_changes import PoeChangeError, PoeModePlans, SCOPE


SITE_REF = "a" * 24
SWITCH_REF = "b" * 24
PORT = 7


class PoeModePlansTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {"poe": 0, "supportPoe": True, "profileOverrideEnable": True}
        self.reads: list[tuple[str, str, int]] = []
        self.writes: list[tuple[str, str, int, dict[str, int]]] = []

        def read(site_ref: str, switch_ref: str, port: int):
            self.reads.append((site_ref, switch_ref, port))
            return dict(self.state)

        def write(site_ref: str, switch_ref: str, port: int, body: dict[str, int]):
            self.writes.append((site_ref, switch_ref, port, dict(body)))
            self.state["poe"] = body["poeMode"]

        self.read = read
        self.write = write
        self.engine = PoeModePlans(read, write, writes_enabled=True)

    def test_preview_is_bounded_warns_and_performs_no_write(self) -> None:
        preview = self.engine.preview(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})
        self.assertEqual(preview["scope"], SCOPE)
        self.assertEqual((preview["site_ref"], preview["switch_ref"], preview["port"]),
                         (SITE_REF, SWITCH_REF, PORT))
        self.assertEqual(preview["before"], {"poeMode": 0})
        self.assertEqual(preview["target"], {"poeMode": 1})
        self.assertEqual(preview["rollback"], {"poeMode": 0})
        self.assertIn("interrupt_power", preview["warning"])
        self.assertTrue(preview["writes_enabled"])
        self.assertEqual(self.reads, [(SITE_REF, SWITCH_REF, PORT)])
        self.assertEqual(self.writes, [])

    def test_default_off_single_put_readback_and_replay_denied(self) -> None:
        self.engine = PoeModePlans(self.read, self.write)
        preview = self.engine.preview(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})
        self.assertFalse(preview["writes_enabled"])
        with self.assertRaisesRegex(PoeChangeError, "writes_disabled"):
            self.engine.apply(preview["plan_id"])
        self.assertEqual(self.writes, [])

        self.engine.writes_enabled = True
        applied = self.engine.apply(preview["plan_id"])
        self.assertEqual(applied["status"], "verified")
        self.assertEqual(applied["before"], {"poeMode": 0})
        self.assertEqual(applied["after"], {"poeMode": 1})
        self.assertEqual(self.writes, [(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})])
        self.assertEqual(self.reads, [(SITE_REF, SWITCH_REF, PORT)] * 3)
        with self.assertRaisesRegex(PoeChangeError, "consumed"):
            self.engine.apply(preview["plan_id"])
        self.assertEqual(len(self.writes), 1)

    def test_noop_bad_inputs_and_fail_closed_preconditions(self) -> None:
        with self.assertRaisesRegex(PoeChangeError, "no_change"):
            self.engine.preview(SITE_REF, SWITCH_REF, PORT, {"poeMode": 0})
        for bad_site in ("x", "A" * 24, "a" * 23):
            with self.subTest(site=bad_site), self.assertRaisesRegex(
                    PoeChangeError, "site_ref_invalid"):
                self.engine.preview(bad_site, SWITCH_REF, PORT, {"poeMode": 1})
        for bad_switch in ("x", "B" * 24, "b" * 23):
            with self.subTest(switch=bad_switch), self.assertRaisesRegex(
                    PoeChangeError, "switch_ref_invalid"):
                self.engine.preview(SITE_REF, bad_switch, PORT, {"poeMode": 1})
        for bad_port in (True, -1, 4097, "7", 7.0):
            with self.subTest(port=bad_port), self.assertRaisesRegex(
                    PoeChangeError, "port_invalid"):
                self.engine.preview(SITE_REF, SWITCH_REF, bad_port, {"poeMode": 1})
        for change in ({}, {"poeMode": True}, {"poeMode": 2}, {"poeMode": 1, "x": 0}):
            with self.subTest(change=change), self.assertRaisesRegex(
                    PoeChangeError, "change_invalid|poe_mode_invalid"):
                self.engine.preview(SITE_REF, SWITCH_REF, PORT, change)

        for state, code in (
            ({"poe": -1, "supportPoe": True, "profileOverrideEnable": True}, "read_state_invalid"),
            ({"poe": 2, "supportPoe": True, "profileOverrideEnable": True}, "read_state_invalid"),
            ({"poe": True, "supportPoe": True, "profileOverrideEnable": True}, "read_state_invalid"),
            ({"poe": 0, "supportPoe": False, "profileOverrideEnable": True}, "poe_unsupported"),
            ({"poe": 0, "supportPoe": True, "profileOverrideEnable": False}, "profile_override_required"),
            ({"poe": 0, "profileOverrideEnable": True}, "read_state_invalid"),
            ({"poe": 0, "supportPoe": 1, "profileOverrideEnable": True}, "read_state_invalid"),
            ({"poe": 0, "supportPoe": True}, "read_state_invalid"),
            ({"poe": 0, "supportPoe": True, "profileOverrideEnable": None}, "read_state_invalid"),
            ({"poe": 0, "supportPoe": True, "profileOverrideEnable": True, "raw": "x"}, "read_state_invalid"),
        ):
            self.engine.read = lambda *_args, state=state: state
            with self.subTest(state=state), self.assertRaisesRegex(PoeChangeError, code):
                self.engine.preview(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})
        self.assertEqual(self.engine.plans, {})
        self.assertEqual(self.writes, [])

    def test_port_boundary_matches_switch_inventory_range(self) -> None:
        for port in (0, 4096):
            with self.subTest(port=port):
                engine = PoeModePlans(self.read, self.write)
                preview = engine.preview(SITE_REF, SWITCH_REF, port, {"poeMode": 1})
                self.assertEqual(preview["port"], port)
        for port in (-1, 4097, True):
            with self.subTest(invalid_port=port), self.assertRaisesRegex(
                    PoeChangeError, "port_invalid"):
                self.engine.preview(SITE_REF, SWITCH_REF, port, {"poeMode": 1})

    def test_stale_and_expired_plans_do_not_write(self) -> None:
        stale = self.engine.preview(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})
        self.state["poe"] = 1
        with self.assertRaisesRegex(PoeChangeError, "state_changed"):
            self.engine.apply(stale["plan_id"])
        self.assertEqual(self.writes, [])

        now = [10.0]
        engine = PoeModePlans(self.read, self.write, writes_enabled=True,
                              ttl_seconds=5, clock=lambda: now[0])
        self.state["poe"] = 0
        expired = engine.preview(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})
        now[0] = 15.0
        with self.assertRaisesRegex(PoeChangeError, "plan_expired"):
            engine.apply(expired["plan_id"])
        self.assertEqual(self.writes, [])

    def test_expiry_during_prewrite_read_blocks_put(self) -> None:
        now = [0.0]
        reads = [0]

        def slow_read(*_args):
            reads[0] += 1
            if reads[0] == 2:
                now[0] = 5.0
            return dict(self.state)

        engine = PoeModePlans(slow_read, self.write, writes_enabled=True,
                              ttl_seconds=5, clock=lambda: now[0])
        preview = engine.preview(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})
        with self.assertRaisesRegex(PoeChangeError, "plan_expired"):
            engine.apply(preview["plan_id"])
        self.assertEqual(self.writes, [])
        self.assertEqual(engine.plans[preview["plan_id"]]["state"], "expired")

    def test_uncertain_put_or_readback_is_in_doubt_and_cannot_replay(self) -> None:
        preview = self.engine.preview(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})

        def uncertain(*_args):
            self.state["poe"] = 1
            raise TimeoutError("private controller detail")

        self.engine.write = uncertain
        with self.assertRaisesRegex(PoeChangeError, "change_in_doubt") as caught:
            self.engine.apply(preview["plan_id"])
        self.assertNotIn("private controller detail", str(caught.exception))
        self.assertEqual(self.engine.plans[preview["plan_id"]]["state"], "in_doubt")
        with self.assertRaisesRegex(PoeChangeError, "consumed"):
            self.engine.apply(preview["plan_id"])

        self.state["poe"] = 0
        mismatch = PoeModePlans(self.read, lambda *_args: None, writes_enabled=True)
        plan = mismatch.preview(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})
        with self.assertRaisesRegex(PoeChangeError, "change_in_doubt"):
            mismatch.apply(plan["plan_id"])
        self.assertEqual(mismatch.plans[plan["plan_id"]]["state"], "in_doubt")
        with self.assertRaisesRegex(PoeChangeError, "consumed"):
            mismatch.apply(plan["plan_id"])

    def test_rollback_requires_a_new_plan_and_write(self) -> None:
        first = self.engine.preview(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})
        applied = self.engine.apply(first["plan_id"])
        rollback = self.engine.preview(SITE_REF, SWITCH_REF, PORT, applied["rollback"])
        self.assertNotEqual(first["plan_id"], rollback["plan_id"])
        self.assertEqual(rollback["target"], {"poeMode": 0})
        rolled_back = self.engine.apply(rollback["plan_id"])
        self.assertEqual(rolled_back["after"], {"poeMode": 0})
        self.assertEqual(self.writes, [
            (SITE_REF, SWITCH_REF, PORT, {"poeMode": 1}),
            (SITE_REF, SWITCH_REF, PORT, {"poeMode": 0}),
        ])

    def test_in_doubt_list_inspect_close_and_replay_are_read_only(self) -> None:
        preview = self.engine.preview(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})
        attempts: list[tuple[str, str, int, dict[str, int]]] = []

        def uncertain(site_ref: str, switch_ref: str, port: int, body: dict[str, int]):
            attempts.append((site_ref, switch_ref, port, dict(body)))
            self.state["poe"] = body["poeMode"]
            raise TimeoutError("private controller detail")

        self.engine.write = uncertain
        with self.assertRaisesRegex(PoeChangeError, "change_in_doubt"):
            self.engine.apply(preview["plan_id"])
        reads_before = len(self.reads)
        listed = self.engine.list_in_doubt()
        self.assertEqual(listed, [{
            "plan_id": preview["plan_id"], "state": "in_doubt", "scope": SCOPE,
            "target_refs": {"site_ref": SITE_REF, "switch_ref": SWITCH_REF, "port": PORT},
        }])
        self.assertEqual(len(self.reads), reads_before)
        self.assertEqual(attempts, [(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})])

        inspected = self.engine.inspect_in_doubt(preview["plan_id"])
        self.assertEqual(len(self.reads), reads_before + 1)
        self.assertEqual(inspected["outcome"], "unknown")
        self.assertEqual(inspected["current_observation"], {
            "status": "observed", "data": {"poeMode": 1}})
        self.assertIn("does_not_prove", inspected["observation_note"])
        self.assertEqual(inspected["target_refs"]["port"], PORT)
        self.assertNotIn("private controller detail", str(inspected))
        self.assertEqual(attempts, [(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})])

        with self.assertRaisesRegex(PoeChangeError, "operator_confirmation_required"):
            self.engine.close_in_doubt(preview["plan_id"], "close")
        closed = self.engine.close_in_doubt(preview["plan_id"], "outcome_unknown_no_retry")
        self.assertEqual(closed["state"], "closed_outcome_unknown")
        self.assertEqual(closed["target_refs"], {
            "site_ref": SITE_REF, "switch_ref": SWITCH_REF, "port": PORT})
        with self.assertRaisesRegex(PoeChangeError, "plan_unknown"):
            self.engine.apply(preview["plan_id"])
        self.assertEqual(attempts, [(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})])

    def test_in_doubt_inspection_stays_unknown_when_read_is_unavailable(self) -> None:
        preview = self.engine.preview(SITE_REF, SWITCH_REF, PORT, {"poeMode": 1})

        def uncertain(*_args):
            raise TimeoutError("write may have landed")

        self.engine.write = uncertain
        with self.assertRaisesRegex(PoeChangeError, "change_in_doubt"):
            self.engine.apply(preview["plan_id"])
        writes_before = list(self.writes)
        self.engine.read = lambda *_args: (_ for _ in ()).throw(
            RuntimeError("private read detail"))
        inspected = self.engine.inspect_in_doubt(preview["plan_id"])
        self.assertEqual(inspected["outcome"], "unknown")
        self.assertEqual(inspected["current_observation"], {"status": "unavailable"})
        self.assertNotIn("private read detail", str(inspected))
        self.assertEqual(self.writes, writes_before)
        with self.assertRaisesRegex(PoeChangeError, "consumed"):
            self.engine.apply(preview["plan_id"])
        self.assertEqual(self.writes, writes_before)


if __name__ == "__main__":
    unittest.main()
