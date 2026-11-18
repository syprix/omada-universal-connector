from __future__ import annotations

import unittest

from app.ap_qos_changes import ApQosChangeError, ApQosPlans, _patch
from app.approval_plans import build_approval_summary


SITE, AP = "a" * 24, "b" * 24


def state(*, split: bool = False) -> dict[str, bool]:
    return {"support2g": True, "support5g": True, "support5g2": split,
            "support6g": True, "deliveryEnable2g": True,
            "deliveryEnable5g": True, "deliveryEnable5g2": False,
            "deliveryEnable6g": True}


class Journal:
    def __init__(self): self.events = []
    def in_doubt_plans(self): return []
    def record_dispatch_intent(self, **event): self.events.append(("intent", event))
    def record_outcome(self, plan_id, outcome): self.events.append(("outcome", plan_id, outcome))
    def close_unknown(self, plan_id, confirmation): self.events.append(("close", plan_id, confirmation))


class ApQosChangeTests(unittest.TestCase):
    def test_patch_uses_first_split_segment_name_and_preserves_supported_bands(self) -> None:
        before = state(split=True)
        self.assertEqual(_patch(before), {"deliveryEnable2g": True,
            "deliveryEnable5g1": True, "deliveryEnable5g2": False,
            "deliveryEnable6g": True})
        before["support5g2"] = False
        self.assertEqual(_patch(before)["deliveryEnable5g"], True)

    def test_preview_binds_complete_state_and_approval_digest(self) -> None:
        current = state(split=True)
        journal = Journal()
        plans = ApQosPlans(lambda *_: current.copy(), lambda *_: None,
                           journal=journal, writes_enabled=True)
        preview = plans.preview(SITE, AP, {"deliveryEnable5g": False},
                                disruption_confirmed=True)
        summary = build_approval_summary("ap-qos", preview["plan_id"], plans)
        self.assertEqual(summary["target_refs"], {"site_ref": SITE, "device_ref": AP})
        self.assertEqual(summary["target"]["deliveryEnable5g"], False)
        self.assertEqual(preview["patch"]["deliveryEnable5g1"], False)
        self.assertEqual(preview["patch"]["deliveryEnable5g2"], False)

    def test_apply_rechecks_journals_and_verifies_full_state(self) -> None:
        current = state(split=True)
        writes = []
        journal = Journal()
        def write(_site, _ap, body):
            writes.append(body)
            current["deliveryEnable2g"] = body["deliveryEnable2g"]
            current["deliveryEnable5g"] = body["deliveryEnable5g1"]
            current["deliveryEnable5g2"] = body["deliveryEnable5g2"]
            current["deliveryEnable6g"] = body["deliveryEnable6g"]
        plans = ApQosPlans(lambda *_: current.copy(), write,
                           journal=journal, writes_enabled=True)
        preview = plans.preview(SITE, AP, {"deliveryEnable5g": False},
                                disruption_confirmed=True)
        result = plans.apply(preview["plan_id"])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(len(writes), 1)
        self.assertEqual([event[0] for event in journal.events], ["intent", "outcome"])

    def test_apply_preserves_only_supported_bands_when_optional_values_are_absent(self) -> None:
        current = {"support2g": True, "support5g": True, "support5g2": False,
                   "support6g": False, "deliveryEnable2g": True,
                   "deliveryEnable5g": True}
        journal = Journal()
        writes = []

        def write(_site, _ap, body):
            writes.append(body)
            current.update(body)

        plans = ApQosPlans(lambda *_: current.copy(), write,
                           journal=journal, writes_enabled=True)
        preview = plans.preview(SITE, AP, {"deliveryEnable5g": False},
                                disruption_confirmed=True)
        summary = build_approval_summary("ap-qos", preview["plan_id"], plans)
        result = plans.apply(preview["plan_id"])

        expected_patch = {"deliveryEnable2g": True, "deliveryEnable5g": False}
        self.assertEqual(summary["target"]["support5g2"], False)
        self.assertNotIn("deliveryEnable5g2", summary["target"])
        self.assertEqual(writes, [expected_patch])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["patch"], expected_patch)
        self.assertEqual([event[0] for event in journal.events], ["intent", "outcome"])

    def test_unsupported_no_change_and_missing_confirmation_are_rejected(self) -> None:
        current = state()
        plans = ApQosPlans(lambda *_: current.copy(), lambda *_: None,
                           journal=Journal(), writes_enabled=True)
        with self.assertRaisesRegex(ApQosChangeError, "disruption_confirmation_required"):
            plans.preview(SITE, AP, {"deliveryEnable2g": False})
        with self.assertRaisesRegex(ApQosChangeError, "ap_qos_band_not_reported_supported"):
            plans.preview(SITE, AP, {"deliveryEnable5g2": True}, disruption_confirmed=True)
        with self.assertRaisesRegex(ApQosChangeError, "no_change"):
            plans.preview(SITE, AP, {"deliveryEnable2g": True}, disruption_confirmed=True)

    def test_state_change_blocks_apply_before_dispatch(self) -> None:
        current = state()
        journal = Journal()
        writes = []
        plans = ApQosPlans(lambda *_: current.copy(), lambda *args: writes.append(args),
                           journal=journal, writes_enabled=True)
        preview = plans.preview(SITE, AP, {"deliveryEnable2g": False},
                                disruption_confirmed=True)
        current["support6g"] = False
        with self.assertRaisesRegex(ApQosChangeError, "state_changed"):
            plans.apply(preview["plan_id"])
        self.assertEqual(writes, [])
        self.assertEqual(journal.events, [])


if __name__ == "__main__":
    unittest.main()
