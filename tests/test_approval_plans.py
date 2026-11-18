import copy
import threading
import unittest

from app.approval_plans import ApprovalPlanError, build_approval_summary
from app.ap_ofdma_changes import ApOfdmaPlans


PID = "a" * 48
SITE, DEVICE, OTHER = "1" * 24, "2" * 24, "3" * 24
HASH = "b" * 64
TAG_ROWS = [{"classType": i, "enable": i != 2, "dscp": str((i + 1) * 8)} for i in range(4)]


class Manager:
    def __init__(self, plan):
        self.lock = threading.RLock()
        self.plans = {PID: plan}


def cases():
    common = {"before_hash": HASH, "expires": 9999999999, "state": "pending"}
    return [
        ("radio", {"target": (SITE, DEVICE), "previous": {"radioSetting2g": {"txPowerLevel": 1}}, "changes": {"radioSetting2g": {"txPowerLevel": 2}}, "has_catalog": False, **common}),
        ("dns-cache", {"site_ref": SITE, "before": {"enable": True, "ttl": 300}, "target": {"enable": False, "ttl": 300}, **common}),
        ("ssid", {"target_refs": (SITE, DEVICE), "before": {"ssidEnable": True}, "target": {"ssidEnable": False}, **common}),
        ("gateway-ipv6", {"site_ref": SITE, "gateway_ref": DEVICE, "before": {"enable": True}, "target": {"enable": False}, **common}),
        ("poe", {"site_ref": SITE, "switch_ref": DEVICE, "port": 4, "before": {"poe": 1, "supportPoe": True, "profileOverrideEnable": True}, "target": {"poeMode": 0}, **common}),
        ("switch-port-status", {"site_ref": SITE, "switch_ref": DEVICE, "port": 4, "before": {"status": 1}, "target": {"status": 0}, **common}),
        ("switch-port-name", {"site_ref": SITE, "switch_ref": DEVICE, "port": 4,
                              "before": {"name": "Old-Uplink"},
                              "target": {"name": "New-Uplink"}, **common}),
        ("site-dpi", {"site_ref": SITE,
                       "before": {"dpi": False, "loggingTraffic": False},
                       "target": {"dpi": True, "loggingTraffic": False}, **common}),
        ("gateway-voip", {"site_ref": SITE,
                            "before": {"enable": False, "sipUdpPort": 5060},
                            "target": {"enable": True, "sipUdpPort": 5060}, **common}),
        ("gateway-tag-qos", {"site_ref": SITE,
                               "before": {"tagConfigList": copy.deepcopy(TAG_ROWS)},
                               "target": {"tagConfigList": [dict(row, enable=(True if row["classType"] == 2 else row["enable"])) for row in TAG_ROWS]}, **common}),
        ("band-steering", {"site_ref": SITE, "before": {"mode": 1}, "target": {"mode": 2}, **common}),
        ("rrm-mode", {"site_ref": SITE,
                       "before": {"mode": 0, "timeRangeEnable": False, "resource": 1,
                                  "timeRangeId": "", "timeRangeAction": 0},
                       "target": {"mode": 1, "timeRangeEnable": False, "resource": 1,
                                  "timeRangeId": "", "timeRangeAction": 0}, **common}),
        ("site-led", {"site_ref": SITE, "before": {"enable": False},
                       "target": {"enable": True}, **common}),
        ("ap-afc", {"site_ref": SITE, "device_ref": DEVICE,
                     "before": {"supportAfc": True, "enable": False},
                     "target": {"enable": True}, **common}),
        ("site-lldp", {"site_ref": SITE, "before": {"enable": False},
                        "target": {"enable": True}, **common}),
        ("ap-channel-limit", {"site_ref": SITE, "device_ref": DEVICE,
                               "before": {"supportChannelLimit": True,
                                          "channelLimitType": 1,
                                          "defaultInstType5g": False,
                                          "defaultInstType6g": True},
                               "target": {"channelLimitType": 2}, **common}),
        ("ap-ofdma", {"site_ref": SITE, "device_ref": DEVICE,
                       "before": {"ofdmaEnable2g": False, "ofdmaEnable5g": False,
                                  "ofdmaEnable5g2": False, "ofdmaEnable6g": False,
                                  "supportOfdma2g": False, "supportOfdma5g": True,
                                  "supportOfdma5g2": False, "supportOfdma6g": False},
                       "target": {"ofdmaEnable2g": False, "ofdmaEnable5g": True,
                                  "ofdmaEnable5g2": False, "ofdmaEnable6g": False,
                                  "supportOfdma2g": False, "supportOfdma5g": True,
                                  "supportOfdma5g2": False, "supportOfdma6g": False},
                       "field": "ofdmaEnable5g", "patch_before": {"ofdmaEnable5g": False},
                       "patch_target": {"ofdmaEnable5g": True}, **common}),
    ]


class ApprovalPlansTests(unittest.TestCase):
    def test_snapshot_is_redacted_detached_and_deterministic(self):
        for operation, plan in cases():
            with self.subTest(operation=operation):
                manager = Manager(copy.deepcopy(plan))
                original = copy.deepcopy(manager.plans)
                summary = build_approval_summary(operation, PID, manager)
                self.assertEqual(summary, build_approval_summary(operation, PID, manager))
                self.assertEqual(len(summary["digest"]), 64)
                self.assertEqual(set(summary), {"operation", "plan_id", "target_refs", "before", "target", "before_hash", "digest"})
                self.assertEqual(manager.plans, original)
                if operation != "switch-port-name":
                    self.assertNotIn("name", repr(summary).lower())
                else:
                    self.assertEqual(summary["before"], {"name": "Old-Uplink"})
                    self.assertEqual(summary["target"], {"name": "New-Uplink"})

    def test_digest_binds_every_summary_value(self):
        for operation, plan in cases():
            with self.subTest(operation=operation):
                baseline = build_approval_summary(operation, PID, Manager(copy.deepcopy(plan)))
                changed = copy.deepcopy(plan)
                changed["before_hash"] = "c" * 64
                self.assertNotEqual(build_approval_summary(operation, PID, Manager(changed))["digest"], baseline["digest"])

                # Every component of the normalized reference set contributes.
                for field in ("site_ref", "device_ref", "ssid_ref", "gateway_ref", "switch_ref"):
                    changed = copy.deepcopy(plan)
                    if operation == "radio" and field in {"site_ref", "device_ref"}:
                        refs = list(changed["target"])
                        refs[0 if field == "site_ref" else 1] = OTHER
                        changed["target"] = tuple(refs)
                    elif operation == "ssid" and field in {"site_ref", "ssid_ref"}:
                        refs = list(changed["target_refs"])
                        refs[0 if field == "site_ref" else 1] = OTHER
                        changed["target_refs"] = tuple(refs)
                    elif field in changed:
                        changed[field] = OTHER
                    else:
                        continue
                    self.assertNotEqual(build_approval_summary(operation, PID, Manager(changed))["digest"], baseline["digest"], field)

                changed = copy.deepcopy(plan)
                if operation == "radio":
                    changed["changes"]["radioSetting2g"]["txPowerLevel"] = 4
                    changed["previous"]["radioSetting2g"]["txPowerLevel"] = 0
                elif operation == "dns-cache":
                    changed["target"]["ttl"] = 301
                    changed["before"]["ttl"] = 301
                elif operation == "ssid":
                    changed["target"]["ssidEnable"] = True
                    changed["before"]["ssidEnable"] = False
                elif operation == "gateway-ipv6":
                    changed["target"]["enable"] = True
                    changed["before"]["enable"] = False
                elif operation == "poe":
                    changed["target"]["poeMode"] = 1
                    changed["before"]["poe"] = 0
                elif operation == "band-steering":
                    changed["target"]["mode"] = 0
                    changed["before"]["mode"] = 1
                elif operation == "rrm-mode":
                    changed["target"]["mode"] = 0
                    changed["before"]["mode"] = 1
                elif operation == "site-led":
                    changed["target"]["enable"] = False
                    changed["before"]["enable"] = True
                elif operation == "ap-afc":
                    changed["target"]["enable"] = False
                    changed["before"]["enable"] = True
                elif operation == "site-lldp":
                    changed["target"]["enable"] = False
                    changed["before"]["enable"] = True
                elif operation == "ap-channel-limit":
                    changed["target"]["channelLimitType"] = 0
                    changed["before"]["channelLimitType"] = 2
                elif operation == "ap-ofdma":
                    changed["target"]["ofdmaEnable5g"] = False
                    changed["before"]["ofdmaEnable5g"] = True
                    changed["patch_before"] = {"ofdmaEnable5g": True}
                    changed["patch_target"] = {"ofdmaEnable5g": False}
                elif operation == "switch-port-name":
                    changed["target"]["name"] = "Another-Uplink"
                elif operation == "site-dpi":
                    changed["before"]["loggingTraffic"] = True
                    changed["target"]["loggingTraffic"] = True
                elif operation == "gateway-voip":
                    changed["before"]["sipUdpPort"] = 5061
                    changed["target"]["sipUdpPort"] = 5061
                elif operation == "gateway-tag-qos":
                    changed["before"]["tagConfigList"][2]["enable"] = True
                    changed["target"]["tagConfigList"][2]["enable"] = False
                else:
                    changed["target"]["status"] = 1
                    changed["before"]["status"] = 0
                self.assertNotEqual(build_approval_summary(operation, PID, Manager(changed))["digest"], baseline["digest"])

    def test_rejects_wrong_operation_id_state_and_extra_or_malformed_fields(self):
        operation, valid = cases()[1]
        for bad_op, bad_id in [("unknown", PID), (operation, "bad")]:
            with self.subTest(operation=bad_op, plan_id=bad_id), self.assertRaises(ApprovalPlanError):
                build_approval_summary(bad_op, bad_id, Manager(copy.deepcopy(valid)))
        mutators = (
            lambda plan: plan.update(state="applied"),
            lambda plan: plan.update(secret="must not leak"),
            lambda plan: plan.update(site_ref="not-an-opaque-ref"),
            lambda plan: plan.update(before={"enable": True, "ttl": 30, "name": "secret"}),
            lambda plan: plan.update(before_hash="invalid"),
        )
        for index, mutate in enumerate(mutators):
            with self.subTest(malformed_case=index):
                bad = copy.deepcopy(valid)
                mutate(bad)
                with self.assertRaises(ApprovalPlanError):
                    build_approval_summary(operation, PID, Manager(bad))

    def test_rejects_missing_plan_and_invalid_manager(self):
        manager = Manager(cases()[0][1])
        with self.assertRaises(ApprovalPlanError):
            build_approval_summary("radio", "c" * 48, manager)
        with self.assertRaises(ApprovalPlanError):
            build_approval_summary("radio", PID, object())

    def test_band_steering_summary_is_site_scoped_and_rejects_bool_modes(self):
        plan = next(plan for operation, plan in cases() if operation == "band-steering")
        summary = build_approval_summary("band-steering", PID, Manager(copy.deepcopy(plan)))
        self.assertEqual(summary["target_refs"], {"site_ref": SITE})
        self.assertEqual(summary["before"], {"mode": 1})
        self.assertEqual(summary["target"], {"mode": 2})
        for bad in (True, 3, 1.0):
            altered = copy.deepcopy(plan)
            altered["target"] = {"mode": bad}
            with self.subTest(mode=bad), self.assertRaises(ApprovalPlanError):
                build_approval_summary("band-steering", PID, Manager(altered))

    def test_rrm_summary_rejects_non_mode_differences_and_malformed_values(self):
        plan = next(plan for operation, plan in cases() if operation == "rrm-mode")
        summary = build_approval_summary("rrm-mode", PID, Manager(copy.deepcopy(plan)))
        self.assertEqual(summary["target_refs"], {"site_ref": SITE})
        self.assertEqual(summary["target"]["mode"], 1)
        for field, value in (("mode", True), ("mode", 2), ("timeRangeEnable", True),
                             ("resource", False), ("resource", 3),
                             ("timeRangeId", "x"), ("timeRangeAction", True),
                             ("timeRangeAction", 2)):
            altered = copy.deepcopy(plan)
            altered["target"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ApprovalPlanError):
                build_approval_summary("rrm-mode", PID, Manager(altered))
            altered = copy.deepcopy(plan)
            altered["before"][field] = value
            with self.subTest(before_field=field, value=value), self.assertRaises(ApprovalPlanError):
                build_approval_summary("rrm-mode", PID, Manager(altered))
        altered = copy.deepcopy(plan)
        altered["target"]["resource"] = 2
        with self.assertRaises(ApprovalPlanError):
            build_approval_summary("rrm-mode", PID, Manager(altered))

    def test_site_led_summary_is_site_scoped_and_bool_strict(self):
        plan = next(plan for operation, plan in cases() if operation == "site-led")
        summary = build_approval_summary("site-led", PID, Manager(copy.deepcopy(plan)))
        self.assertEqual(summary["target_refs"], {"site_ref": SITE})
        self.assertEqual(summary["before"], {"enable": False})
        self.assertEqual(summary["target"], {"enable": True})
        for bad in (0, 1, "true", None):
            altered = copy.deepcopy(plan)
            altered["target"] = {"enable": bad}
            with self.subTest(enable=bad), self.assertRaises(ApprovalPlanError):
                build_approval_summary("site-led", PID, Manager(altered))

    def test_ap_afc_summary_binds_refs_support_and_exact_states(self):
        plan = next(plan for operation, plan in cases() if operation == "ap-afc")
        summary = build_approval_summary("ap-afc", PID, Manager(copy.deepcopy(plan)))
        self.assertEqual(summary["target_refs"], {"site_ref": SITE, "device_ref": DEVICE})
        self.assertEqual(summary["before"], {"supportAfc": True, "enable": False})
        self.assertEqual(summary["target"], {"enable": True})
        for before, target in (
            ({"supportAfc": False, "enable": False}, {"enable": True}),
            ({"supportAfc": 1, "enable": False}, {"enable": True}),
            ({"supportAfc": True, "enable": 0}, {"enable": True}),
            ({"supportAfc": True, "enable": False}, {"enable": 1}),
            ({"supportAfc": True, "enable": False, "extra": True}, {"enable": True}),
        ):
            altered = copy.deepcopy(plan)
            altered["before"], altered["target"] = before, target
            with self.subTest(before=before, target=target), self.assertRaises(ApprovalPlanError):
                build_approval_summary("ap-afc", PID, Manager(altered))

    def test_site_lldp_summary_is_site_scoped_and_bool_strict(self):
        plan = next(plan for operation, plan in cases() if operation == "site-lldp")
        summary = build_approval_summary("site-lldp", PID, Manager(copy.deepcopy(plan)))
        self.assertEqual(summary["target_refs"], {"site_ref": SITE})
        self.assertEqual(summary["before"], {"enable": False})
        self.assertEqual(summary["target"], {"enable": True})
        for bad in (0, 1, "false", None):
            altered = copy.deepcopy(plan)
            altered["target"] = {"enable": bad}
            with self.subTest(enable=bad), self.assertRaises(ApprovalPlanError):
                build_approval_summary("site-lldp", PID, Manager(altered))

    def test_ap_channel_limit_summary_binds_full_before_state_and_target(self):
        plan = next(plan for operation, plan in cases() if operation == "ap-channel-limit")
        summary = build_approval_summary("ap-channel-limit", PID, Manager(copy.deepcopy(plan)))
        self.assertEqual(summary["target_refs"], {"site_ref": SITE, "device_ref": DEVICE})
        self.assertEqual(summary["before"], plan["before"])
        self.assertEqual(summary["target"], {"channelLimitType": 2})
        for field, bad in (("supportChannelLimit", False), ("supportChannelLimit", 1),
                           ("channelLimitType", True), ("channelLimitType", 3),
                           ("defaultInstType5g", 1), ("defaultInstType6g", "false")):
            altered = copy.deepcopy(plan)
            altered["before"][field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(ApprovalPlanError):
                build_approval_summary("ap-channel-limit", PID, Manager(altered))
        for bad in (True, -1, 3):
            altered = copy.deepcopy(plan)
            altered["target"]["channelLimitType"] = bad
            with self.subTest(target=bad), self.assertRaises(ApprovalPlanError):
                build_approval_summary("ap-channel-limit", PID, Manager(altered))

    def test_ap_ofdma_summary_binds_complete_states_and_one_supported_change(self):
        plan = next(plan for operation, plan in cases() if operation == "ap-ofdma")
        summary = build_approval_summary("ap-ofdma", PID, Manager(copy.deepcopy(plan)))
        self.assertEqual(summary["target_refs"], {"site_ref": SITE, "device_ref": DEVICE})
        self.assertEqual(summary["before"], plan["before"])
        self.assertEqual(summary["target"], plan["target"])
        mutations = []
        altered = copy.deepcopy(plan)
        altered["target"]["ofdmaEnable2g"] = True
        mutations.append(altered)  # two enable fields differ
        altered = copy.deepcopy(plan)
        altered["target"]["supportOfdma5g"] = False
        mutations.append(altered)  # support state is immutable
        altered = copy.deepcopy(plan)
        altered["before"]["supportOfdma5g"] = False
        altered["target"]["supportOfdma5g"] = False
        mutations.append(altered)  # changed band was not supported
        altered = copy.deepcopy(plan)
        altered["before"].pop("supportOfdma5g")
        mutations.append(altered)  # all eight exact fields are required
        altered = copy.deepcopy(plan)
        altered["target"]["ofdmaEnable5g"] = 1
        mutations.append(altered)  # booleans are strict
        for key, value in (("field", "ofdmaEnable2g"),
                           ("patch_before", {"ofdmaEnable2g": False}),
                           ("patch_target", {"ofdmaEnable2g": True}),
                           ("patch_before", {"ofdmaEnable5g": 1}),
                           ("patch_target", {"ofdmaEnable5g": False, "extra": True})):
            altered = copy.deepcopy(plan)
            altered[key] = value
            mutations.append(altered)
        altered = copy.deepcopy(plan)
        del altered["field"]
        mutations.append(altered)
        for malformed in mutations:
            with self.subTest(plan=malformed), self.assertRaises(ApprovalPlanError):
                build_approval_summary("ap-ofdma", PID, Manager(malformed))

    def test_ap_ofdma_summary_accepts_full_real_manager_preview(self):
        before = {"ofdmaEnable2g": False, "ofdmaEnable5g": False,
                  "ofdmaEnable5g2": True, "ofdmaEnable6g": False,
                  "supportOfdma2g": True, "supportOfdma5g": True,
                  "supportOfdma5g2": False, "supportOfdma6g": True}
        manager = ApOfdmaPlans(lambda _site, _device: copy.deepcopy(before),
                               lambda *_args: None)
        preview = manager.preview(SITE, DEVICE, {"ofdmaEnable5g": True},
                                  disruption_confirmed=True)
        summary = build_approval_summary("ap-ofdma", preview["plan_id"], manager)
        self.assertEqual(summary["target_refs"], {"site_ref": SITE, "device_ref": DEVICE})
        self.assertEqual(summary["before"], before)
        self.assertEqual(summary["target"], {**before, "ofdmaEnable5g": True})

    def test_switch_port_name_approval_binds_exact_names_and_rejects_unsafe_text(self):
        plan = next(plan for operation, plan in cases() if operation == "switch-port-name")
        baseline = build_approval_summary("switch-port-name", PID, Manager(copy.deepcopy(plan)))
        self.assertEqual(baseline["target_refs"],
                         {"site_ref": SITE, "switch_ref": DEVICE, "port": 4})
        self.assertEqual(baseline["before"], {"name": "Old-Uplink"})
        self.assertEqual(baseline["target"], {"name": "New-Uplink"})

        for legacy_name in ("", 'Legacy?"Label'):
            legacy = copy.deepcopy(plan)
            legacy["before"] = {"name": legacy_name}
            summary = build_approval_summary("switch-port-name", PID, Manager(legacy))
            self.assertEqual(summary["before"], {"name": legacy_name})

        for field, replacement in (("before", "Old-Other"), ("target", "New-Other")):
            altered = copy.deepcopy(plan)
            altered[field] = {"name": replacement}
            self.assertNotEqual(
                build_approval_summary("switch-port-name", PID, Manager(altered))["digest"],
                baseline["digest"])

        for bad_name in ("", " leading", "trailing ", "?", 'has"quote',
                         "line\nbreak", "esc\x1b", "bidi\u202e", "e\u0301",
                         "x" * 129, 1, None):
            altered = copy.deepcopy(plan)
            altered["target"] = {"name": bad_name}
            with self.subTest(name=repr(bad_name)), self.assertRaises(ApprovalPlanError):
                build_approval_summary("switch-port-name", PID, Manager(altered))

        for bad_old in ("leading ", "line\nbreak", "bidi\u202e", "e\u0301", "x" * 129):
            altered = copy.deepcopy(plan)
            altered["before"] = {"name": bad_old}
            with self.subTest(old_name=repr(bad_old)), self.assertRaises(ApprovalPlanError):
                build_approval_summary("switch-port-name", PID, Manager(altered))

        altered = copy.deepcopy(plan)
        altered["target"] = altered["before"]
        with self.assertRaises(ApprovalPlanError):
            build_approval_summary("switch-port-name", PID, Manager(altered))

    def test_site_dpi_summary_binds_both_bool_states_and_one_field_delta(self):
        plan = next(plan for operation, plan in cases() if operation == "site-dpi")
        baseline = build_approval_summary("site-dpi", PID, Manager(copy.deepcopy(plan)))
        self.assertEqual(baseline["target_refs"], {"site_ref": SITE})
        self.assertEqual(baseline["before"], {"dpi": False, "loggingTraffic": False})
        self.assertEqual(baseline["target"], {"dpi": True, "loggingTraffic": False})

        for field in ("dpi", "loggingTraffic"):
            altered = copy.deepcopy(plan)
            if field == "dpi":
                altered["before"][field] = True
                altered["target"][field] = False
            else:
                altered["before"][field] = True
                altered["target"][field] = True
            summary = build_approval_summary("site-dpi", PID, Manager(altered))
            self.assertNotEqual(summary["digest"], baseline["digest"])
        altered = copy.deepcopy(plan)
        altered["site_ref"] = OTHER
        self.assertNotEqual(build_approval_summary("site-dpi", PID, Manager(altered))["digest"],
                            baseline["digest"])

        malformed = []
        for key in ({"dpi"}, {"dpi", "loggingTraffic", "extra"}):
            bad = copy.deepcopy(plan)
            bad["target"] = {field: False for field in key}
            malformed.append(bad)
        for field, value in (("dpi", 1), ("loggingTraffic", None)):
            bad = copy.deepcopy(plan)
            bad["target"][field] = value
            malformed.append(bad)
        bad = copy.deepcopy(plan)
        bad["target"] = {"dpi": True, "loggingTraffic": True}
        malformed.append(bad)  # two changed fields
        bad = copy.deepcopy(plan)
        bad["target"] = copy.deepcopy(bad["before"])
        malformed.append(bad)  # no change
        for bad in malformed:
            with self.subTest(plan=bad), self.assertRaises(ApprovalPlanError):
                build_approval_summary("site-dpi", PID, Manager(bad))

    def test_gateway_voip_summary_binds_full_site_state_and_only_enable_changes(self):
        plan = next(plan for operation, plan in cases() if operation == "gateway-voip")
        baseline = build_approval_summary("gateway-voip", PID, Manager(copy.deepcopy(plan)))
        self.assertEqual(baseline["target_refs"], {"site_ref": SITE})
        self.assertEqual(baseline["before"], {"enable": False, "sipUdpPort": 5060})
        self.assertEqual(baseline["target"], {"enable": True, "sipUdpPort": 5060})

        changed_site = copy.deepcopy(plan)
        changed_site["site_ref"] = OTHER
        self.assertNotEqual(build_approval_summary("gateway-voip", PID, Manager(changed_site))["digest"],
                            baseline["digest"])
        changed_port = copy.deepcopy(plan)
        changed_port["before"]["sipUdpPort"] = 5061
        changed_port["target"]["sipUdpPort"] = 5061
        self.assertNotEqual(build_approval_summary("gateway-voip", PID, Manager(changed_port))["digest"],
                            baseline["digest"])

        malformed = []
        bad = copy.deepcopy(plan); bad["before"].pop("sipUdpPort"); malformed.append(bad)
        bad = copy.deepcopy(plan); bad["target"]["sipUdpPort"] = 5061; malformed.append(bad)
        bad = copy.deepcopy(plan); bad["target"]["enable"] = False; malformed.append(bad)
        bad = copy.deepcopy(plan); bad["before"]["sipUdpPort"] = True; malformed.append(bad)
        bad = copy.deepcopy(plan); bad["target"]["sipUdpPort"] = 65536; malformed.append(bad)
        bad = copy.deepcopy(plan); bad["unexpected"] = True; malformed.append(bad)
        for bad in malformed:
            with self.subTest(plan=bad), self.assertRaises(ApprovalPlanError):
                build_approval_summary("gateway-voip", PID, Manager(bad))

    def test_gateway_tag_qos_preserves_order_and_binds_full_state(self):
        operation, plan = next(item for item in cases() if item[0] == "gateway-tag-qos")
        summary = build_approval_summary(operation, PID, Manager(copy.deepcopy(plan)))
        self.assertEqual(summary["target_refs"], {"site_ref": SITE})
        self.assertEqual(summary["before"]["tagConfigList"], TAG_ROWS)
        self.assertEqual(summary["target"]["tagConfigList"][2]["enable"], True)
        for mutate in (
            lambda p: p["target"]["tagConfigList"].reverse(),
            lambda p: p["target"]["tagConfigList"][0].update(dscp="16"),
            lambda p: p["target"]["tagConfigList"][0].update(classType=1),
            lambda p: p["target"]["tagConfigList"][1].update(enable=not p["target"]["tagConfigList"][1]["enable"]),
            lambda p: p["target"]["tagConfigList"].append(dict(p["target"]["tagConfigList"][0])),
        ):
            bad = copy.deepcopy(plan)
            mutate(bad)
            with self.subTest(plan=bad), self.assertRaises(ApprovalPlanError):
                build_approval_summary(operation, PID, Manager(bad))


if __name__ == "__main__":
    unittest.main()
