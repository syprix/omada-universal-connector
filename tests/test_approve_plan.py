import hashlib
import io
import json
import os
import tempfile
import unittest

from app.operator_approval import OperatorApprovalError, load_operator_key, verify_approval
from tools.approve_plan import ApprovalInputError, _ApprovalTerminal, approve


OPERATOR = "op_" + "d" * 24
KEY = b"k" * 32


def request_bytes():
    payload = {
        "operation": "switch-port-status", "plan_id": "a" * 48,
        "target_refs": {"site_ref": "1" * 24, "switch_ref": "2" * 24, "port": 7},
        "before": {"status": 1}, "target": {"status": 0}, "before_hash": "b" * 64,
    }
    payload["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload).encode("utf-8")


def port_name_bytes(*, before="Gebäude-Uplink", target="Büro-Uplink"):
    payload = {
        "operation": "switch-port-name", "plan_id": "a" * 48,
        "target_refs": {"site_ref": "1" * 24, "switch_ref": "2" * 24, "port": 7},
        "before": {"name": before}, "target": {"name": target},
        "before_hash": "b" * 64,
    }
    payload["digest"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload, ensure_ascii=True).encode("ascii")


def site_dpi_bytes(*, before=None, target=None):
    payload = {
        "operation": "site-dpi", "plan_id": "a" * 48,
        "target_refs": {"site_ref": "1" * 24},
        "before": before if before is not None else {"dpi": False, "loggingTraffic": False},
        "target": target if target is not None else {"dpi": False, "loggingTraffic": True},
        "before_hash": "b" * 64,
    }
    payload["digest"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload, ensure_ascii=True).encode("ascii")


def gateway_voip_bytes(*, before=None, target=None, refs=None):
    payload = {
        "operation": "gateway-voip", "plan_id": "a" * 48,
        "target_refs": refs if refs is not None else {"site_ref": "1" * 24},
        "before": before if before is not None else {"enable": False, "sipUdpPort": 5060},
        "target": target if target is not None else {"enable": True, "sipUdpPort": 5060},
        "before_hash": "b" * 64,
    }
    payload["digest"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload, ensure_ascii=True).encode("ascii")


def gateway_tag_qos_bytes(*, before=None, target=None, refs=None):
    rows = [{"classType": i, "enable": i != 2, "dscp": str((i + 1) * 8)} for i in range(4)]
    target_rows = [dict(row, enable=(True if row["classType"] == 2 else row["enable"])) for row in rows]
    payload = {
        "operation": "gateway-tag-qos", "plan_id": "a" * 48,
        "target_refs": refs if refs is not None else {"site_ref": "1" * 24},
        "before": before if before is not None else {"tagConfigList": rows},
        "target": target if target is not None else {"tagConfigList": target_rows},
        "before_hash": "b" * 64,
    }
    payload["digest"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload, ensure_ascii=True).encode("ascii")


def radio_bytes(*, target=None):
    payload = {
        "operation": "radio", "plan_id": "a" * 48,
        "target_refs": {"site_ref": "1" * 24, "device_ref": "2" * 24},
        "before": {"radioSetting2g": {"channel": 6}},
        "target": target if target is not None else {"radioSetting2g": {"channel": "11", "freq": 2462}},
        "before_hash": "b" * 64,
    }
    payload["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload).encode("utf-8")


def band_steering_bytes(*, before=None, target=None, refs=None):
    payload = {
        "operation": "band-steering", "plan_id": "a" * 48,
        "target_refs": refs if refs is not None else {"site_ref": "1" * 24},
        "before": before if before is not None else {"mode": 1},
        "target": target if target is not None else {"mode": 2},
        "before_hash": "b" * 64,
    }
    payload["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload).encode("utf-8")


def rrm_mode_bytes(*, before=None, target=None, refs=None):
    state_before = {"mode": 0, "timeRangeEnable": False, "resource": 1,
                    "timeRangeId": "", "timeRangeAction": 0}
    state_target = dict(state_before, mode=1)
    payload = {
        "operation": "rrm-mode", "plan_id": "a" * 48,
        "target_refs": refs if refs is not None else {"site_ref": "1" * 24},
        "before": before if before is not None else state_before,
        "target": target if target is not None else state_target,
        "before_hash": "b" * 64,
    }
    payload["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload).encode("utf-8")


def site_led_bytes(*, before=None, target=None, refs=None):
    payload = {
        "operation": "site-led", "plan_id": "a" * 48,
        "target_refs": refs if refs is not None else {"site_ref": "1" * 24},
        "before": before if before is not None else {"enable": False},
        "target": target if target is not None else {"enable": True},
        "before_hash": "b" * 64,
    }
    payload["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload).encode("utf-8")


def ap_afc_bytes(*, before=None, target=None, refs=None):
    payload = {
        "operation": "ap-afc", "plan_id": "a" * 48,
        "target_refs": refs if refs is not None else {"site_ref": "1" * 24, "device_ref": "2" * 24},
        "before": before if before is not None else {"supportAfc": True, "enable": False},
        "target": target if target is not None else {"enable": True},
        "before_hash": "b" * 64,
    }
    payload["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload).encode("utf-8")


def site_lldp_bytes(*, before=None, target=None, refs=None):
    payload = {
        "operation": "site-lldp", "plan_id": "a" * 48,
        "target_refs": refs if refs is not None else {"site_ref": "1" * 24},
        "before": before if before is not None else {"enable": False},
        "target": target if target is not None else {"enable": True},
        "before_hash": "b" * 64,
    }
    payload["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload).encode("utf-8")


def ap_channel_limit_bytes(*, before=None, target=None, refs=None):
    payload = {
        "operation": "ap-channel-limit", "plan_id": "a" * 48,
        "target_refs": refs if refs is not None else {"site_ref": "1" * 24, "device_ref": "2" * 24},
        "before": before if before is not None else {"supportChannelLimit": True,
                                                      "channelLimitType": 1,
                                                      "defaultInstType5g": False,
                                                      "defaultInstType6g": True},
        "target": target if target is not None else {"channelLimitType": 2},
        "before_hash": "b" * 64,
    }
    payload["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload).encode("utf-8")


def ap_ofdma_bytes(*, before=None, target=None, refs=None):
    before_state = {"ofdmaEnable2g": False, "ofdmaEnable5g": False,
                    "ofdmaEnable5g2": False, "ofdmaEnable6g": False,
                    "supportOfdma2g": False, "supportOfdma5g": True,
                    "supportOfdma5g2": False, "supportOfdma6g": False}
    target_state = dict(before_state, ofdmaEnable5g=True)
    payload = {
        "operation": "ap-ofdma", "plan_id": "a" * 48,
        "target_refs": refs if refs is not None else {"site_ref": "1" * 24, "device_ref": "2" * 24},
        "before": before if before is not None else before_state,
        "target": target if target is not None else target_state,
        "before_hash": "b" * 64,
    }
    payload["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload).encode("utf-8")


def ap_qos_bytes(*, before=None, target=None, refs=None):
    before_state = {"support2g": True, "support5g": True, "support5g2": False,
                    "support6g": False, "deliveryEnable2g": True,
                    "deliveryEnable5g": True}
    target_state = dict(before_state, deliveryEnable5g=False)
    payload = {"operation": "ap-qos", "plan_id": "a" * 48,
        "target_refs": refs if refs is not None else {"site_ref": "1" * 24, "device_ref": "2" * 24},
        "before": before if before is not None else before_state,
        "target": target if target is not None else target_state,
        "before_hash": "b" * 64}
    payload["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return json.dumps(payload).encode("utf-8")


class FakeTTY(io.StringIO):
    def __init__(self, response):
        super().__init__()
        self.response = response

    def isatty(self):
        return True

    def readline(self, *args, **kwargs):
        return self.response


class ApprovePlanTests(unittest.TestCase):
    def test_ap_qos_operator_approval_accepts_omitted_unsupported_band_values(self):
        data = ap_qos_bytes()
        envelope = approve(data, FakeTTY("FREIGEBEN\n"), key_file="unused",
                           operator_id=OPERATOR, now=100, key_loader=lambda _: KEY)
        request = json.loads(data)
        self.assertEqual(verify_approval(KEY, envelope, operation="ap-qos",
            plan_id=request["plan_id"], plan_digest=request["digest"], now=101), OPERATOR)

        invalid = json.loads(data)
        invalid["before"]["support5g"] = False
        invalid["before"]["support5g2"] = True
        payload = {key: value for key, value in invalid.items() if key != "digest"}
        invalid["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True,
            separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
        with self.assertRaises(ApprovalInputError):
            approve(json.dumps(invalid).encode(), FakeTTY("FREIGEBEN\n"),
                    key_file="unused", operator_id=OPERATOR, now=100,
                    key_loader=lambda _: KEY)

        malformed = []
        for field, mutate in (
            ("missing-supported-value", lambda b, t: b.pop("deliveryEnable5g")),
            ("unexpected-unsupported-value", lambda b, t: (b.update(deliveryEnable6g=False),
                                                              t.update(deliveryEnable6g=False))),
            ("changed-support-flag", lambda b, t: t.update(support2g=False)),
        ):
            request = json.loads(ap_qos_bytes())
            mutate(request["before"], request["target"])
            payload = {key: value for key, value in request.items() if key != "digest"}
            request["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True,
                separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
            malformed.append((field, json.dumps(request).encode()))
        for label, request_data in malformed:
            with self.subTest(case=label), self.assertRaises(ApprovalInputError):
                approve(request_data, FakeTTY("FREIGEBEN\n"), key_file="unused",
                        operator_id=OPERATOR, now=100,
                        key_loader=lambda _: self.fail("must not load key"))

    def test_ap_ofdma_summary_binds_all_fields_and_warns_about_unverified_patch(self):
        data = ap_ofdma_bytes()
        tty = FakeTTY("FREIGEBEN\n")
        envelope = approve(data, tty, key_file="unused", operator_id=OPERATOR,
                           now=100, key_loader=lambda _: KEY)
        request = json.loads(data)
        self.assertEqual(verify_approval(KEY, envelope, operation="ap-ofdma",
                                         plan_id=request["plan_id"],
                                         plan_digest=request["digest"], now=100), OPERATOR)
        self.assertIn('"operation": "ap-ofdma"', tty.getvalue())
        self.assertIn("nicht live geprüft", tty.getvalue())
        for malformed in (
            ap_ofdma_bytes(before={"ofdmaEnable5g": False}),
            ap_ofdma_bytes(before={**json.loads(ap_ofdma_bytes())["before"],
                                   "supportOfdma5g": False}),
            ap_ofdma_bytes(target={**json.loads(ap_ofdma_bytes())["target"],
                                   "ofdmaEnable2g": True}),
            ap_ofdma_bytes(target={**json.loads(ap_ofdma_bytes())["target"],
                                   "supportOfdma5g": False}),
            ap_ofdma_bytes(target={**json.loads(ap_ofdma_bytes())["target"],
                                   "ofdmaEnable5g": 1}),
            ap_ofdma_bytes(refs={"site_ref": "bad", "device_ref": "2" * 24}),
        ):
            with self.subTest(data=malformed), self.assertRaises(ApprovalInputError):
                approve(malformed, FakeTTY("FREIGEBEN\n"), key_file="unused",
                        operator_id=OPERATOR, key_loader=lambda _: self.fail("must not load key"))

    def test_ap_channel_limit_summary_binds_full_state_and_controller_warning(self):
        data = ap_channel_limit_bytes()
        tty = FakeTTY("FREIGEBEN\n")
        envelope = approve(data, tty, key_file="unused", operator_id=OPERATOR,
                           now=100, key_loader=lambda _: KEY)
        request = json.loads(data)
        self.assertEqual(verify_approval(KEY, envelope, operation="ap-channel-limit",
                                         plan_id=request["plan_id"],
                                         plan_digest=request["digest"], now=100), OPERATOR)
        self.assertIn('"operation": "ap-channel-limit"', tty.getvalue())
        self.assertIn("konkrete Wirkung der AP-Kanalbegrenzung hängt vom Controller ab", tty.getvalue())
        for malformed in (
            ap_channel_limit_bytes(before={"supportChannelLimit": False, "channelLimitType": 1,
                                           "defaultInstType5g": False, "defaultInstType6g": True}),
            ap_channel_limit_bytes(before={"supportChannelLimit": True, "channelLimitType": True,
                                           "defaultInstType5g": False, "defaultInstType6g": True}),
            ap_channel_limit_bytes(before={"supportChannelLimit": True, "channelLimitType": 1,
                                           "defaultInstType5g": 0, "defaultInstType6g": True}),
            ap_channel_limit_bytes(target={"channelLimitType": False}),
            ap_channel_limit_bytes(target={"channelLimitType": 3}),
            ap_channel_limit_bytes(refs={"site_ref": "bad", "device_ref": "2" * 24}),
        ):
            with self.subTest(data=malformed), self.assertRaises(ApprovalInputError):
                approve(malformed, FakeTTY("FREIGEBEN\n"), key_file="unused",
                        operator_id=OPERATOR, key_loader=lambda _: self.fail("must not load key"))

    def test_site_lldp_summary_has_controller_dependent_effect_warning(self):
        data = site_lldp_bytes()
        tty = FakeTTY("FREIGEBEN\n")
        envelope = approve(data, tty, key_file="unused", operator_id=OPERATOR,
                           now=100, key_loader=lambda _: KEY)
        request = json.loads(data)
        self.assertEqual(verify_approval(KEY, envelope, operation="site-lldp",
                                         plan_id=request["plan_id"],
                                         plan_digest=request["digest"], now=100), OPERATOR)
        self.assertIn('"operation": "site-lldp"', tty.getvalue())
        self.assertIn("Wirkung auf konkrete Geräte hängt vom Controller ab", tty.getvalue())
        for malformed in (site_lldp_bytes(before={"enable": 0}),
                          site_lldp_bytes(target={"enable": "true"}),
                          site_lldp_bytes(refs={"site_ref": "bad"}),
                          site_lldp_bytes(refs={"site_ref": "1" * 24, "extra": True})):
            with self.subTest(data=malformed), self.assertRaises(ApprovalInputError):
                approve(malformed, FakeTTY("FREIGEBEN\n"), key_file="unused",
                        operator_id=OPERATOR, key_loader=lambda _: self.fail("must not load key"))

    def test_ap_afc_summary_warns_only_of_possible_ap_behavior_change(self):
        data = ap_afc_bytes()
        tty = FakeTTY("FREIGEBEN\n")
        envelope = approve(data, tty, key_file="unused", operator_id=OPERATOR,
                           now=100, key_loader=lambda _: KEY)
        request = json.loads(data)
        self.assertEqual(verify_approval(KEY, envelope, operation="ap-afc",
                                         plan_id=request["plan_id"],
                                         plan_digest=request["digest"], now=100), OPERATOR)
        self.assertIn('"operation": "ap-afc"', tty.getvalue())
        self.assertIn("kann das Verhalten des AP beeinflussen", tty.getvalue())
        for malformed in (
            ap_afc_bytes(before={"supportAfc": True, "enable": 0}),
            ap_afc_bytes(before={"supportAfc": False, "enable": False}),
            ap_afc_bytes(target={"enable": "true"}),
            ap_afc_bytes(refs={"site_ref": "bad", "device_ref": "2" * 24}),
            ap_afc_bytes(refs={"site_ref": "1" * 24, "device_ref": "2" * 24, "extra": 1}),
        ):
            with self.subTest(data=malformed), self.assertRaises(ApprovalInputError):
                approve(malformed, FakeTTY("FREIGEBEN\n"), key_file="unused",
                        operator_id=OPERATOR, key_loader=lambda _: self.fail("must not load key"))

    def test_site_led_summary_includes_controller_dependent_effect_warning(self):
        data = site_led_bytes()
        tty = FakeTTY("FREIGEBEN\n")
        envelope = approve(data, tty, key_file="unused", operator_id=OPERATOR,
                           now=100, key_loader=lambda _: KEY)
        request = json.loads(data)
        self.assertEqual(verify_approval(KEY, envelope, operation="site-led",
                                         plan_id=request["plan_id"],
                                         plan_digest=request["digest"], now=100), OPERATOR)
        self.assertIn('"operation": "site-led"', tty.getvalue())
        self.assertIn("Wirkungsumfang der LED-Änderung hängt vom Controller ab", tty.getvalue())
        for malformed in (site_led_bytes(before={"enable": 0}),
                          site_led_bytes(target={"enable": "true"}),
                          site_led_bytes(refs={"site_ref": "bad"})):
            with self.subTest(data=malformed), self.assertRaises(ApprovalInputError):
                approve(malformed, FakeTTY("FREIGEBEN\n"), key_file="unused",
                        operator_id=OPERATOR, key_loader=lambda _: self.fail("must not load key"))

    def test_rrm_mode_summary_warns_and_requires_exact_state(self):
        data = rrm_mode_bytes()
        tty = FakeTTY("FREIGEBEN\n")
        envelope = approve(data, tty, key_file="unused", operator_id=OPERATOR,
                           now=100, key_loader=lambda _: KEY)
        request = json.loads(data)
        self.assertEqual(verify_approval(KEY, envelope, operation="rrm-mode",
                                         plan_id=request["plan_id"],
                                         plan_digest=request["digest"], now=100), OPERATOR)
        self.assertIn('"operation": "rrm-mode"', tty.getvalue())
        self.assertIn("RF-Optimierung kann WLAN-Funkparameter ändern", tty.getvalue())
        for malformed in (
            rrm_mode_bytes(before={"mode": True}),
            rrm_mode_bytes(target={"mode": 2}),
            rrm_mode_bytes(target={"mode": 1, "timeRangeEnable": True,
                                  "resource": 1, "timeRangeId": "", "timeRangeAction": 0}),
            rrm_mode_bytes(target={"mode": 1, "timeRangeEnable": False,
                                  "resource": 2, "timeRangeId": "", "timeRangeAction": 0}),
        ):
            with self.subTest(data=malformed), self.assertRaises(ApprovalInputError):
                approve(malformed, FakeTTY("FREIGEBEN\n"), key_file="unused",
                        operator_id=OPERATOR, key_loader=lambda _: self.fail("must not load key"))

    def test_band_steering_summary_warns_and_signs_only_after_confirmation(self):
        data = band_steering_bytes()
        tty = FakeTTY("FREIGEBEN\n")
        envelope = approve(data, tty, key_file="unused", operator_id=OPERATOR,
                           now=100, key_loader=lambda _: KEY)
        request = json.loads(data)
        self.assertEqual(verify_approval(KEY, envelope, operation="band-steering",
                                         plan_id=request["plan_id"],
                                         plan_digest=request["digest"], now=100), OPERATOR)
        self.assertIn('"operation": "band-steering"', tty.getvalue())
        self.assertIn("kurzzeitig unterbrechen", tty.getvalue())

        for malformed in (band_steering_bytes(before={"mode": True}),
                          band_steering_bytes(target={"mode": 3}),
                          band_steering_bytes(refs={"site_ref": "not-a-ref"})):
            with self.subTest(data=malformed), self.assertRaises(ApprovalInputError):
                approve(malformed, FakeTTY("FREIGEBEN\n"), key_file="unused",
                        operator_id=OPERATOR, key_loader=lambda _: self.fail("must not load key"))

    def test_interactive_approval_with_existing_protected_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "operator.key")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as key_file:
                key_file.write(KEY)
            tty = FakeTTY("FREIGEBEN\n")
            envelope = approve(request_bytes(), tty, key_file=path, operator_id=OPERATOR,
                               expires_in=60, now=1000)
            self.assertEqual(load_operator_key(path), KEY)
            self.assertEqual(verify_approval(KEY, envelope, operation="switch-port-status",
                                             plan_id="a" * 48, plan_digest=json.loads(request_bytes())["digest"], now=1000), OPERATOR)
            self.assertIn('"operation": "switch-port-status"', tty.getvalue())
            self.assertIn("Verwaltungszugang trennen", tty.getvalue())

    def test_switch_port_name_signs_exact_names_and_displays_them_json_escaped(self):
        data = port_name_bytes()
        request = json.loads(data)
        tty = FakeTTY("FREIGEBEN\n")
        envelope = approve(data, tty, key_file="unused", operator_id=OPERATOR,
                           now=100, key_loader=lambda _: KEY)
        self.assertEqual(verify_approval(KEY, envelope, operation="switch-port-name",
                                         plan_id=request["plan_id"],
                                         plan_digest=request["digest"], now=100), OPERATOR)
        shown = tty.getvalue()
        self.assertIn('"name": "Geb\\u00e4ude-Uplink"', shown)
        self.assertIn('"name": "B\\u00fcro-Uplink"', shown)
        # The preview is rendered through json.dumps(ensure_ascii=True), so
        # non-ASCII labels are shown as escaped JSON rather than raw controls.
        self.assertIn('"operation": "switch-port-name"', shown)
        self.assertIn("Portname", shown)

        changed = json.loads(port_name_bytes(target="Büro-Client"))
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, envelope, operation="switch-port-name",
                            plan_id=changed["plan_id"], plan_digest=changed["digest"], now=100)

        changed_before = json.loads(port_name_bytes(before="Legacy?\"Label"))
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, envelope, operation="switch-port-name",
                            plan_id=changed_before["plan_id"],
                            plan_digest=changed_before["digest"], now=100)

        # Empty and legacy punctuation are allowed only in the old value.
        old_empty = json.loads(port_name_bytes(before=""))
        empty_tty = FakeTTY("FREIGEBEN\n")
        empty_envelope = approve(json.dumps(old_empty).encode(), empty_tty,
                                 key_file="unused", operator_id=OPERATOR,
                                 now=100, key_loader=lambda _: KEY)
        self.assertEqual(verify_approval(KEY, empty_envelope,
                                         operation="switch-port-name",
                                         plan_id=old_empty["plan_id"],
                                         plan_digest=old_empty["digest"], now=100), OPERATOR)
        self.assertIn('"name": ""', empty_tty.getvalue())
        legacy_tty = FakeTTY("FREIGEBEN\n")
        legacy = port_name_bytes(before='Legacy?"Label')
        legacy_envelope = approve(legacy, legacy_tty, key_file="unused",
                                  operator_id=OPERATOR, now=100,
                                  key_loader=lambda _: KEY)
        self.assertEqual(verify_approval(KEY, legacy_envelope,
                                         operation="switch-port-name",
                                         plan_id=json.loads(legacy)["plan_id"],
                                         plan_digest=json.loads(legacy)["digest"],
                                         now=100), OPERATOR)
        self.assertIn('Legacy?\\\"Label', legacy_tty.getvalue())

    def test_switch_port_name_rejects_unsafe_or_malformed_values_without_signing(self):
        calls = []
        loader = lambda _: calls.append("load") or KEY
        signer = lambda *args, **kwargs: calls.append("sign") or {}
        malformed = (
            port_name_bytes(before="old", target="old"),
            port_name_bytes(target=" leading"),
            port_name_bytes(target="trailing "),
            port_name_bytes(target="has?question"),
            port_name_bytes(target='has"quote'),
            port_name_bytes(target="line\nbreak"),
            port_name_bytes(target="bidi\u202e"),
            port_name_bytes(target="e\u0301"),
            port_name_bytes(target="x" * 129),
            port_name_bytes(before="bad\nlegacy"),
            port_name_bytes(before="e\u0301"),
        )
        for data in malformed:
            with self.subTest(data=data):
                with self.assertRaises(ApprovalInputError) as caught:
                    approve(data, FakeTTY("FREIGEBEN\n"), key_file="x",
                            operator_id=OPERATOR, key_loader=loader, signer=signer)
                self.assertNotIn("line", str(caught.exception))
                self.assertNotIn("bidi", str(caught.exception))
        altered = json.loads(port_name_bytes())
        altered["target"]["name"] = "private-name"
        with self.assertRaises(ApprovalInputError):
            approve(json.dumps(altered).encode(), FakeTTY("FREIGEBEN\n"),
                    key_file="x", operator_id=OPERATOR,
                    key_loader=loader, signer=signer)
        self.assertEqual(calls, [])

    def test_site_dpi_approval_binds_both_states_and_warns_for_usage_logging(self):
        data = site_dpi_bytes()
        request = json.loads(data)
        tty = FakeTTY("FREIGEBEN\n")
        envelope = approve(data, tty, key_file="unused", operator_id=OPERATOR,
                           now=100, key_loader=lambda _: KEY)
        self.assertEqual(verify_approval(KEY, envelope, operation="site-dpi",
                                         plan_id=request["plan_id"],
                                         plan_digest=request["digest"], now=100), OPERATOR)
        shown = tty.getvalue()
        self.assertIn('"dpi": false', shown)
        self.assertIn('"loggingTraffic": true', shown)
        self.assertIn("loggingTraffic=true kann Nutzungsdaten protokollieren", shown)

        changed = json.loads(site_dpi_bytes(
            before={"dpi": True, "loggingTraffic": False},
            target={"dpi": False, "loggingTraffic": False}))
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, envelope, operation="site-dpi",
                            plan_id=changed["plan_id"], plan_digest=changed["digest"], now=100)

    def test_site_dpi_rejects_partial_non_bool_noop_or_multi_field_change(self):
        calls = []
        loader = lambda _: calls.append("load") or KEY
        signer = lambda *args, **kwargs: calls.append("sign") or {}
        malformed = (
            site_dpi_bytes(before={"dpi": False}, target={"dpi": True}),
            site_dpi_bytes(target={"dpi": True, "loggingTraffic": True}),
            site_dpi_bytes(target={"dpi": False, "loggingTraffic": False}),
            site_dpi_bytes(target={"dpi": 1, "loggingTraffic": False}),
            site_dpi_bytes(target={"dpi": False, "loggingTraffic": False, "extra": True}),
        )
        for data in malformed:
            with self.subTest(data=data), self.assertRaises(ApprovalInputError):
                approve(data, FakeTTY("FREIGEBEN\n"), key_file="unused",
                        operator_id=OPERATOR, key_loader=loader, signer=signer)
        self.assertEqual(calls, [])

    def test_gateway_voip_approval_binds_full_state_and_warns_about_voice_effects(self):
        data = gateway_voip_bytes()
        request = json.loads(data)
        tty = FakeTTY("FREIGEBEN\n")
        envelope = approve(data, tty, key_file="unused", operator_id=OPERATOR,
                           now=100, key_loader=lambda _: KEY)
        self.assertEqual(verify_approval(KEY, envelope, operation="gateway-voip",
                                         plan_id=request["plan_id"],
                                         plan_digest=request["digest"], now=100), OPERATOR)
        shown = tty.getvalue()
        self.assertIn('"sipUdpPort": 5060', shown)
        self.assertIn("VoIP-Priorisierung", shown)
        self.assertIn("nicht garantiert", shown)

        changed_site = json.loads(gateway_voip_bytes(refs={"site_ref": "2" * 24}))
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, envelope, operation="gateway-voip",
                            plan_id=changed_site["plan_id"],
                            plan_digest=changed_site["digest"], now=100)

    def test_gateway_voip_rejects_missing_port_invalid_delta_and_bad_values(self):
        calls = []
        loader = lambda _: calls.append("load") or KEY
        signer = lambda *args, **kwargs: calls.append("sign") or {}
        malformed = (
            gateway_voip_bytes(before={"enable": False},
                               target={"enable": True, "sipUdpPort": 5060}),
            gateway_voip_bytes(target={"enable": False, "sipUdpPort": 5060}),
            gateway_voip_bytes(target={"enable": True, "sipUdpPort": 5061}),
            gateway_voip_bytes(target={"enable": True, "sipUdpPort": True}),
            gateway_voip_bytes(target={"enable": True, "sipUdpPort": 65536}),
            gateway_voip_bytes(target={"enable": True, "sipUdpPort": 5060,
                                        "unreviewed": 1}),
        )
        for data in malformed:
            with self.subTest(data=data), self.assertRaises(ApprovalInputError):
                approve(data, FakeTTY("FREIGEBEN\n"), key_file="unused",
                        operator_id=OPERATOR, key_loader=loader, signer=signer)
        self.assertEqual(calls, [])

    def test_gateway_tag_qos_approval_binds_full_order_and_warns(self):
        data = gateway_tag_qos_bytes()
        request = json.loads(data)
        tty = FakeTTY("FREIGEBEN\n")
        envelope = approve(data, tty, key_file="unused", operator_id=OPERATOR,
                           now=100, key_loader=lambda _: KEY)
        self.assertEqual(verify_approval(KEY, envelope, operation="gateway-tag-qos",
                                         plan_id=request["plan_id"],
                                         plan_digest=request["digest"], now=100), OPERATOR)
        shown = tty.getvalue()
        self.assertIn("Standortweite Gateway-QoS-Kennzeichnung", shown)
        self.assertIn('"classType": 0', shown)
        self.assertIn('"dscp": "8"', shown)
        for change in ("reverse", "dscp", "enable"):
            altered = json.loads(data)
            if change == "reverse":
                altered["target"]["tagConfigList"].reverse()
            elif change == "dscp":
                altered["target"]["tagConfigList"][0]["dscp"] = "16"
            else:
                altered["target"]["tagConfigList"][1]["enable"] = not altered["target"]["tagConfigList"][1]["enable"]
            altered["digest"] = hashlib.sha256(json.dumps(
                {k: altered[k] for k in ("operation", "plan_id", "target_refs", "before", "target", "before_hash")},
                sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
            with self.subTest(change=change), self.assertRaises(ApprovalInputError):
                approve(json.dumps(altered).encode(), FakeTTY("FREIGEBEN\n"), key_file="unused",
                        operator_id=OPERATOR, now=100, key_loader=lambda _: KEY)

    def test_gateway_tag_qos_rejects_invalid_class_dscp_and_unknown_fields(self):
        base = json.loads(gateway_tag_qos_bytes())
        malformed = []
        for kind in ("duplicate_class", "unknown_dscp", "integer_dscp", "extra_field", "missing_class"):
            value = json.loads(json.dumps(base))
            rows = value["target"]["tagConfigList"]
            if kind == "duplicate_class": rows[1]["classType"] = 0
            elif kind == "unknown_dscp": rows[1]["dscp"] = "08"
            elif kind == "integer_dscp": rows[1]["dscp"] = 8
            elif kind == "extra_field": rows[1]["name"] = "private"
            else: rows.pop()
            value["digest"] = hashlib.sha256(json.dumps(
                {k: value[k] for k in ("operation", "plan_id", "target_refs", "before", "target", "before_hash")},
                sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
            malformed.append(json.dumps(value).encode())
        calls = []
        for data in malformed:
            with self.assertRaises(ApprovalInputError):
                approve(data, FakeTTY("FREIGEBEN\n"), key_file="unused", operator_id=OPERATOR,
                        key_loader=lambda _: calls.append("load") or KEY,
                        signer=lambda *a, **kw: calls.append("sign") or {})
        self.assertEqual(calls, [])

    def test_accepts_preview_and_escapes_terminal_controls(self):
        parsed = json.loads(request_bytes())
        preview = {"approval_request": parsed, "warning": "caution\x1b[31m"}
        tty = FakeTTY("FREIGEBEN\n")
        result = approve(json.dumps(preview).encode(), tty, key_file="unused", operator_id=OPERATOR,
                         now=20, key_loader=lambda _: KEY)
        self.assertIn('\\u001b', tty.getvalue())
        self.assertEqual(result["expires_at"], 80)

    def test_invalid_digest_refusal_and_missing_tty_never_load_or_sign(self):
        calls = []
        loader = lambda _: calls.append("load") or KEY
        signer = lambda *args, **kwargs: calls.append("sign") or {}
        bad = json.loads(request_bytes())
        bad["target"]["status"] = 1
        with self.assertRaises(ApprovalInputError):
            approve(json.dumps(bad).encode(), FakeTTY("FREIGEBEN\n"), key_file="x", operator_id=OPERATOR,
                    key_loader=loader, signer=signer)
        with self.assertRaises(ApprovalInputError):
            approve(request_bytes(), io.StringIO("FREIGEBEN\n"), key_file="x", operator_id=OPERATOR,
                    key_loader=loader, signer=signer)
        with self.assertRaises(ApprovalInputError):
            approve(request_bytes(), FakeTTY("nein\n"), key_file="x", operator_id=OPERATOR,
                    key_loader=loader, signer=signer)
        self.assertEqual(calls, [])

    def test_malformed_radio_shapes_and_huge_channel_are_rejected_safely(self):
        calls = []
        loader = lambda _: calls.append("load") or KEY
        signer = lambda *args, **kwargs: calls.append("sign") or {}
        malformed = (
            radio_bytes(target={}),  # Missing target band previously risked KeyError.
            radio_bytes(target={"radioSetting2g": {"channel": "9" * 10000, "freq": 2462}}),
            radio_bytes(target={"radioSetting2g": {"channel": "11", "freq": "2462"}}),
            radio_bytes(target={"radioSetting2g": {"channel": "11", "freq": 2462, "extra": True}}),
        )
        for data in malformed:
            with self.subTest(length=len(data)):
                with self.assertRaises(ApprovalInputError):
                    approve(data, FakeTTY("FREIGEBEN\n"), key_file="x", operator_id=OPERATOR,
                            key_loader=loader, signer=signer)
        self.assertEqual(calls, [])

    def test_unsupported_five_ghz_channel_is_not_signed(self):
        request = json.loads(radio_bytes())
        request["before"] = {"radioSetting5g": {"channel": 36}}
        request["target"] = {"radioSetting5g": {"channel": "40", "freq": 5200}}
        payload = {key: value for key, value in request.items() if key != "digest"}
        request["digest"] = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
        with self.assertRaises(ApprovalInputError):
            approve(json.dumps(request).encode(), FakeTTY("FREIGEBEN\n"),
                    key_file="unused", operator_id=OPERATOR,
                    key_loader=lambda _: self.fail("must not load key"))

    def test_operator_id_and_expiry_are_bounded(self):
        for kwargs in ({"operator_id": "person-name"}, {"expires_in": 121}, {"expires_in": 0}):
            args = {"key_file": "unused", "operator_id": OPERATOR, "key_loader": lambda _: KEY}
            args.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ApprovalInputError):
                approve(request_bytes(), FakeTTY("FREIGEBEN\n"), **args)


class TerminalStream(io.StringIO):
    def isatty(self):
        return True


class ApprovalTerminalTests(unittest.TestCase):
    def test_combines_read_and_write_terminal_streams(self):
        reader = TerminalStream("FREIGEBEN\\n")
        writer = TerminalStream()
        terminal = _ApprovalTerminal(reader, writer)

        self.assertTrue(terminal.isatty())
        terminal.write("confirm: ")
        terminal.flush()
        self.assertEqual(terminal.readline(), "FREIGEBEN\\n")
        self.assertEqual(writer.getvalue(), "confirm: ")


if __name__ == "__main__":
    unittest.main()
