from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from app import ap_ofdma_changes as ofdma


SITE = "a" * 24
DEVICE = "b" * 24
FIELDS = (
    "ofdmaEnable2g", "ofdmaEnable5g", "ofdmaEnable5g2", "ofdmaEnable6g",
    "supportOfdma2g", "supportOfdma5g", "supportOfdma5g2", "supportOfdma6g",
)


def default_state() -> dict[str, bool]:
    return {field: True for field in FIELDS}


class FakeJournal:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.events: list[object] = []
        self.fail_intent = False
        self.after_intent = None

    def in_doubt_plans(self) -> list[dict[str, object]]:
        return [copy.deepcopy(row) for row in self.rows if row.get("state") == "in_doubt"]

    def record_dispatch_intent(self, **event: object) -> None:
        if self.fail_intent:
            raise OSError("private journal path")
        row = {**copy.deepcopy(event), "state": "in_doubt"}
        self.rows.append(row)
        self.events.append(("intent", copy.deepcopy(event)))
        if self.after_intent:
            self.after_intent()

    def record_outcome(self, plan_id: str, outcome: str) -> None:
        self.events.append(("outcome", plan_id, outcome))
        if outcome == "verified_readback":
            for row in self.rows:
                if row.get("plan_id") == plan_id:
                    row["state"] = "verified"

    def close_unknown(self, plan_id: str, confirmation: str) -> None:
        self.events.append(("close", plan_id, confirmation))
        for row in self.rows:
            if row.get("plan_id") == plan_id:
                row["state"] = "closed"


class ApOfdmaPlansTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = default_state()
        self.writes: list[tuple[str, str, dict[str, bool]]] = []
        self.journal = FakeJournal()

    def read(self, site_ref: str, device_ref: str) -> dict[str, bool]:
        self.assertEqual((site_ref, device_ref), (SITE, DEVICE))
        return dict(self.state)

    def write(self, site_ref: str, device_ref: str, patch_body: dict[str, bool]) -> None:
        self.writes.append((site_ref, device_ref, dict(patch_body)))
        self.state.update(patch_body)

    def manager(self, **kwargs: object) -> ofdma.ApOfdmaPlans:
        return ofdma.ApOfdmaPlans(self.read, self.write, **kwargs)

    def preview(self, manager: ofdma.ApOfdmaPlans, field: str = "ofdmaEnable5g",
                enabled: bool = False) -> dict[str, object]:
        return manager.preview(SITE, DEVICE, {field: enabled}, disruption_confirmed=True)

    def test_preview_binds_full_state_and_warns_about_partial_patch(self) -> None:
        manager = self.manager()
        preview = self.preview(manager)
        expected = default_state()
        target = dict(expected, ofdmaEnable5g=False)
        self.assertEqual(preview["before"], expected)
        self.assertEqual(preview["target"], target)
        self.assertEqual(preview["band_field"], "ofdmaEnable5g")
        self.assertEqual(preview["expires_in_seconds"], 300)
        self.assertFalse(preview["writes_enabled"])
        self.assertTrue(preview["rollback_requires_new_plan"])
        self.assertEqual(preview["warning"],
                         "ofdma_partial_patch_effect_unknown_other_settings_might_be_affected")
        self.assertEqual(self.writes, [])

    def test_validates_exact_eight_bool_state_single_bool_change_and_confirmation(self) -> None:
        manager = self.manager()
        for change in (
            {}, {"ofdmaEnable2g": True, "ofdmaEnable5g": False},
            {"supportOfdma2g": False}, {"ofdmaEnable2g": 1},
            {"ofdmaEnable9g": True},
        ):
            with self.subTest(change=change), self.assertRaises(ofdma.ApOfdmaChangeError):
                manager.preview(SITE, DEVICE, change, disruption_confirmed=True)
        for state in (
            {}, {**default_state(), "supportOfdma6g": 1},
            {**default_state(), "unexpected": False},
        ):
            broken = ofdma.ApOfdmaPlans(lambda _s, _d, v=state: v, self.write)
            with self.subTest(state=state), self.assertRaisesRegex(
                    ofdma.ApOfdmaChangeError, "ofdma_state_invalid"):
                self.preview(broken)
        with self.assertRaisesRegex(ofdma.ApOfdmaChangeError, "disruption_confirmation_required"):
            manager.preview(SITE, DEVICE, {"ofdmaEnable5g": False})
        with self.assertRaisesRegex(ofdma.ApOfdmaChangeError, "no_change"):
            self.preview(manager, "ofdmaEnable5g", True)

    def test_unsupported_band_blocks_without_inferred_hardware_claim(self) -> None:
        self.state["supportOfdma2g"] = False
        manager = self.manager()
        with self.assertRaisesRegex(ofdma.ApOfdmaChangeError, "ofdma_band_not_reported_supported") as ctx:
            self.preview(manager, "ofdmaEnable2g", False)
        self.assertNotIn("hardware", str(ctx.exception))
        self.assertNotIn("firmware", str(ctx.exception))
        self.assertEqual(self.writes, [])

    def test_default_off_journal_required_and_write_uses_only_single_field(self) -> None:
        manager = self.manager(writes_enabled=True, require_journal=True)
        plan_id = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(ofdma.ApOfdmaChangeError, "journal_required"):
            manager.apply(plan_id)
        self.assertEqual(self.writes, [])

        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan_id = self.preview(manager)["plan_id"]
        result = manager.apply(plan_id)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.writes, [(SITE, DEVICE, {"ofdmaEnable5g": False})])
        event = self.journal.events[0][1]
        self.assertEqual(event["operation"], "ap-ofdma")
        self.assertEqual(event["target_refs"], {"site_ref": SITE, "device_ref": DEVICE})
        self.assertEqual(event["before"], {"ofdmaEnable5g": True})
        self.assertEqual(event["target"], {"ofdmaEnable5g": False})
        self.assertEqual(self.journal.events[-1], ("outcome", plan_id, "verified_readback"))
        with self.assertRaisesRegex(ofdma.ApOfdmaChangeError, "plan_already_consumed"):
            manager.apply(plan_id)
        self.assertEqual(len(self.writes), 1)

    def test_stale_full_state_includes_every_support_and_enable_bit(self) -> None:
        for changed_field in ("supportOfdma5g", "supportOfdma2g", "ofdmaEnable6g"):
            with self.subTest(changed_field=changed_field):
                self.state = default_state()
                manager = self.manager(writes_enabled=True, journal=self.journal,
                                       require_journal=True)
                plan_id = self.preview(manager)["plan_id"]
                self.state[changed_field] = False
                with self.assertRaises(ofdma.ApOfdmaChangeError):
                    manager.apply(plan_id)
                self.assertEqual(self.writes, [])
                self.assertEqual(manager.plans[plan_id]["state"], "stale")

    def test_postread_requires_all_other_fields_unchanged_else_in_doubt(self) -> None:
        manager = self.manager(writes_enabled=True, journal=self.journal,
                               require_journal=True)
        plan_id = self.preview(manager)["plan_id"]

        def side_effect(site_ref: str, device_ref: str, patch_body: dict[str, bool]) -> None:
            self.writes.append((site_ref, device_ref, dict(patch_body)))
            self.state.update(patch_body)
            self.state["ofdmaEnable2g"] = False

        manager.write = side_effect
        with self.assertRaisesRegex(ofdma.ApOfdmaChangeError, "change_in_doubt"):
            manager.apply(plan_id)
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(manager.plans[plan_id]["state"], "in_doubt")
        with self.assertRaisesRegex(ofdma.ApOfdmaChangeError, "plan_already_consumed"):
            manager.apply(plan_id)
        self.assertEqual(len(self.writes), 1)

    def test_intent_failure_never_writes_and_exposes_no_exception_details(self) -> None:
        self.journal.fail_intent = True
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan_id = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(ofdma.ApOfdmaChangeError, "journal_unavailable") as ctx:
            manager.apply(plan_id)
        self.assertNotIn("private", str(ctx.exception))
        self.assertEqual(manager.plans[plan_id]["state"], "in_doubt")
        self.assertEqual(self.writes, [])

    def test_expiry_is_checked_after_durable_intent(self) -> None:
        now = [0.0]
        self.journal.after_intent = lambda: now.__setitem__(0, 300.0)
        manager = ofdma.ApOfdmaPlans(self.read, self.write, writes_enabled=True,
                                     clock=lambda: now[0], journal=self.journal,
                                     require_journal=True)
        plan_id = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(ofdma.ApOfdmaChangeError, "plan_expired"):
            manager.apply(plan_id)
        self.assertEqual(self.writes, [])
        self.assertEqual(manager.plans[plan_id]["state"], "in_doubt")

    def test_timeout_becomes_in_doubt_and_replay_is_blocked(self) -> None:
        def timeout(_site: str, _device: str, _patch: dict[str, bool]) -> None:
            self.writes.append((SITE, DEVICE, {"ofdmaEnable5g": False}))
            raise TimeoutError("private host")

        manager = self.manager(writes_enabled=True, journal=self.journal,
                               require_journal=True)
        manager.write = timeout
        plan_id = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(ofdma.ApOfdmaChangeError, "change_in_doubt"):
            manager.apply(plan_id)
        self.assertEqual(manager.plans[plan_id]["state"], "in_doubt")
        with self.assertRaisesRegex(ofdma.ApOfdmaChangeError, "plan_already_consumed"):
            manager.apply(plan_id)
        self.assertEqual(len(self.writes), 1)

    def test_recovery_keeps_only_minimal_change_and_cannot_replay(self) -> None:
        plan_id = "c" * 48
        self.journal.rows = [{
            "operation": ofdma.OPERATION, "plan_id": plan_id,
            "target_refs": {"site_ref": SITE, "device_ref": DEVICE},
            "before": {"ofdmaEnable6g": True},
            "target": {"ofdmaEnable6g": False}, "state": "in_doubt",
        }]
        with patch.object(ofdma, "ALLOWED_JOURNAL_OPERATIONS",
                          frozenset(ofdma.ALLOWED_JOURNAL_OPERATIONS) | {ofdma.OPERATION}):
            recovered = self.manager(writes_enabled=True, journal=self.journal,
                                     require_journal=True)
        plan = recovered.plans[plan_id]
        self.assertEqual(plan["before"], {"ofdmaEnable6g": True})
        self.assertEqual(plan["target"], {"ofdmaEnable6g": False})
        self.assertNotIn("supportOfdma6g", plan["before"])
        self.assertEqual(recovered.list_in_doubt()[0]["target_refs"],
                         {"site_ref": SITE, "device_ref": DEVICE})
        with self.assertRaisesRegex(ofdma.ApOfdmaChangeError, "plan_already_consumed"):
            recovered.apply(plan_id)
        inspected = recovered.inspect_in_doubt(plan_id)
        self.assertEqual(inspected["outcome"], "unknown")
        self.assertEqual(inspected["observation_note"],
                         "current_state_does_not_prove_original_write_outcome")
        self.assertEqual(self.writes, [])

    def test_failed_or_malformed_readback_is_safe(self) -> None:
        bad = {**default_state(), "supportOfdma5g": 1}
        manager = ofdma.ApOfdmaPlans(lambda _s, _d: bad, self.write)
        with self.assertRaisesRegex(ofdma.ApOfdmaChangeError, "ofdma_state_invalid"):
            self.preview(manager)
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()
