from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from app.operator_approval import (
    MAX_APPROVAL_TTL_SECONDS,
    OperatorApprovalError,
    load_operator_key,
    parse_approval,
    sign_approval,
    verify_approval,
)


KEY = b"k" * 32
OTHER_KEY = b"x" * 32
OPERATION = "switch-port-status"
PLAN_ID = "a" * 48
PLAN_DIGEST = "b" * 64
OPERATOR_ID = "op_" + "c" * 24
NOW = 2_000_000_000


class OperatorApprovalTests(unittest.TestCase):
    def token(self, **changes):
        result = sign_approval(KEY, operation=OPERATION, plan_id=PLAN_ID,
                               plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                               expires_at=NOW + 120, now=NOW)
        result.update(changes)
        return result

    def test_sign_and_verify_bind_all_required_fields(self) -> None:
        approval = self.token()
        self.assertEqual(set(approval), {"version", "operation", "plan_id", "plan_digest",
                                         "operator_id", "expires_at", "nonce", "signature"})
        self.assertRegex(approval["nonce"], r"\A[0-9a-f]{32}\Z")
        self.assertEqual(verify_approval(KEY, approval, operation=OPERATION,
                                         plan_id=PLAN_ID, plan_digest=PLAN_DIGEST,
                                         now=NOW), OPERATOR_ID)
        self.assertEqual(verify_approval(KEY, json.dumps(approval), operation=OPERATION,
                                         plan_id=PLAN_ID, plan_digest=PLAN_DIGEST,
                                         now=NOW), OPERATOR_ID)
        second = self.token()
        self.assertNotEqual(second["nonce"], approval["nonce"])
        self.assertNotEqual(second["signature"], approval["signature"])
        for operation, plan_id, digest in (
            ("ssid", PLAN_ID, PLAN_DIGEST),
            (OPERATION, "d" * 48, PLAN_DIGEST),
            (OPERATION, PLAN_ID, "e" * 64),
        ):
            with self.subTest(operation=operation, plan_id=plan_id, digest=digest), \
                    self.assertRaises(OperatorApprovalError):
                verify_approval(KEY, approval, operation=operation,
                                plan_id=plan_id, plan_digest=digest, now=NOW)
        changed_operator = dict(approval, operator_id="op_" + "d" * 24)
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, changed_operator, operation=OPERATION,
                            plan_id=PLAN_ID, plan_digest=PLAN_DIGEST, now=NOW)

    def test_band_steering_is_allowlisted_but_unknown_operations_are_not(self) -> None:
        approval = sign_approval(KEY, operation="band-steering", plan_id=PLAN_ID,
                                 plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                                 expires_at=NOW + 60, now=NOW)
        self.assertEqual(verify_approval(KEY, approval, operation="band-steering",
                                         plan_id=PLAN_ID, plan_digest=PLAN_DIGEST,
                                         now=NOW), OPERATOR_ID)
        with self.assertRaises(OperatorApprovalError):
            sign_approval(KEY, operation="band-steering-extra", plan_id=PLAN_ID,
                          plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                          expires_at=NOW + 60, now=NOW)

    def test_rrm_mode_is_allowlisted_and_signature_binds_operation(self) -> None:
        approval = sign_approval(KEY, operation="rrm-mode", plan_id=PLAN_ID,
                                 plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                                 expires_at=NOW + 60, now=NOW)
        self.assertEqual(verify_approval(KEY, approval, operation="rrm-mode",
                                         plan_id=PLAN_ID, plan_digest=PLAN_DIGEST,
                                         now=NOW), OPERATOR_ID)
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, approval, operation="band-steering",
                            plan_id=PLAN_ID, plan_digest=PLAN_DIGEST, now=NOW)

    def test_site_led_is_allowlisted_and_signature_binds_operation(self) -> None:
        approval = sign_approval(KEY, operation="site-led", plan_id=PLAN_ID,
                                 plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                                 expires_at=NOW + 60, now=NOW)
        self.assertEqual(verify_approval(KEY, approval, operation="site-led",
                                         plan_id=PLAN_ID, plan_digest=PLAN_DIGEST,
                                         now=NOW), OPERATOR_ID)
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, approval, operation="rrm-mode",
                            plan_id=PLAN_ID, plan_digest=PLAN_DIGEST, now=NOW)

    def test_ap_afc_is_allowlisted_and_signature_binds_operation(self) -> None:
        approval = sign_approval(KEY, operation="ap-afc", plan_id=PLAN_ID,
                                 plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                                 expires_at=NOW + 60, now=NOW)
        self.assertEqual(verify_approval(KEY, approval, operation="ap-afc",
                                         plan_id=PLAN_ID, plan_digest=PLAN_DIGEST,
                                         now=NOW), OPERATOR_ID)
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, approval, operation="site-led",
                            plan_id=PLAN_ID, plan_digest=PLAN_DIGEST, now=NOW)

    def test_site_lldp_is_allowlisted_and_signature_binds_operation(self) -> None:
        approval = sign_approval(KEY, operation="site-lldp", plan_id=PLAN_ID,
                                 plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                                 expires_at=NOW + 60, now=NOW)
        self.assertEqual(verify_approval(KEY, approval, operation="site-lldp",
                                         plan_id=PLAN_ID, plan_digest=PLAN_DIGEST,
                                         now=NOW), OPERATOR_ID)
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, approval, operation="site-led",
                            plan_id=PLAN_ID, plan_digest=PLAN_DIGEST, now=NOW)

    def test_ap_channel_limit_is_allowlisted_and_signature_binds_operation(self) -> None:
        approval = sign_approval(KEY, operation="ap-channel-limit", plan_id=PLAN_ID,
                                 plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                                 expires_at=NOW + 60, now=NOW)
        self.assertEqual(verify_approval(KEY, approval, operation="ap-channel-limit",
                                         plan_id=PLAN_ID, plan_digest=PLAN_DIGEST,
                                         now=NOW), OPERATOR_ID)
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, approval, operation="site-lldp",
                            plan_id=PLAN_ID, plan_digest=PLAN_DIGEST, now=NOW)

    def test_ap_ofdma_is_allowlisted_and_signature_binds_operation(self) -> None:
        approval = sign_approval(KEY, operation="ap-ofdma", plan_id=PLAN_ID,
                                 plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                                 expires_at=NOW + 60, now=NOW)
        self.assertEqual(verify_approval(KEY, approval, operation="ap-ofdma",
                                         plan_id=PLAN_ID, plan_digest=PLAN_DIGEST,
                                         now=NOW), OPERATOR_ID)
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, approval, operation="ap-channel-limit",
                            plan_id=PLAN_ID, plan_digest=PLAN_DIGEST, now=NOW)

    def test_switch_port_name_is_allowlisted_and_signature_binds_operation(self) -> None:
        approval = sign_approval(KEY, operation="switch-port-name", plan_id=PLAN_ID,
                                 plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                                 expires_at=NOW + 60, now=NOW)
        self.assertEqual(verify_approval(KEY, approval, operation="switch-port-name",
                                         plan_id=PLAN_ID, plan_digest=PLAN_DIGEST,
                                         now=NOW), OPERATOR_ID)
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, approval, operation="switch-port-status",
                            plan_id=PLAN_ID, plan_digest=PLAN_DIGEST, now=NOW)

    def test_site_dpi_is_allowlisted_and_signature_binds_operation(self) -> None:
        approval = sign_approval(KEY, operation="site-dpi", plan_id=PLAN_ID,
                                 plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                                 expires_at=NOW + 60, now=NOW)
        self.assertEqual(verify_approval(KEY, approval, operation="site-dpi",
                                         plan_id=PLAN_ID, plan_digest=PLAN_DIGEST,
                                         now=NOW), OPERATOR_ID)
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, approval, operation="site-led",
                            plan_id=PLAN_ID, plan_digest=PLAN_DIGEST, now=NOW)

    def test_gateway_voip_is_allowlisted_and_signature_binds_operation(self) -> None:
        approval = sign_approval(KEY, operation="gateway-voip", plan_id=PLAN_ID,
                                 plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                                 expires_at=NOW + 60, now=NOW)
        self.assertEqual(verify_approval(KEY, approval, operation="gateway-voip",
                                         plan_id=PLAN_ID, plan_digest=PLAN_DIGEST,
                                         now=NOW), OPERATOR_ID)
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, approval, operation="site-dpi",
                            plan_id=PLAN_ID, plan_digest=PLAN_DIGEST, now=NOW)

    def test_gateway_tag_qos_is_allowlisted_and_signature_binds_operation(self) -> None:
        approval = sign_approval(KEY, operation="gateway-tag-qos", plan_id=PLAN_ID,
                                 plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                                 expires_at=NOW + 60, now=NOW)
        self.assertEqual(verify_approval(KEY, approval, operation="gateway-tag-qos",
                                         plan_id=PLAN_ID, plan_digest=PLAN_DIGEST,
                                         now=NOW), OPERATOR_ID)
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, approval, operation="gateway-voip",
                            plan_id=PLAN_ID, plan_digest=PLAN_DIGEST, now=NOW)

    def test_rejects_wrong_key_operation_plan_digest_and_expiry(self) -> None:
        approval = self.token()
        cases = (
            (OTHER_KEY, approval, OPERATION, PLAN_ID, PLAN_DIGEST, NOW),
            (KEY, approval, "not-an-operation", PLAN_ID, PLAN_DIGEST, NOW),
            (KEY, approval, OPERATION, "bad-plan", PLAN_DIGEST, NOW),
            (KEY, approval, OPERATION, PLAN_ID, "not-a-digest", NOW),
            (KEY, approval, OPERATION, PLAN_ID, PLAN_DIGEST, NOW + 120),
        )
        for key, value, operation, plan_id, digest, now in cases:
            with self.subTest(operation=operation, plan_id=plan_id, now=now), \
                    self.assertRaises(OperatorApprovalError):
                verify_approval(key, value, operation=operation, plan_id=plan_id,
                                plan_digest=digest, now=now)
        for expiry in (NOW, NOW - 1, NOW + MAX_APPROVAL_TTL_SECONDS + 1, True, 1.5):
            with self.subTest(expiry=expiry), self.assertRaises(OperatorApprovalError):
                sign_approval(KEY, operation=OPERATION, plan_id=PLAN_ID,
                              plan_digest=PLAN_DIGEST, operator_id=OPERATOR_ID,
                              expires_at=expiry, now=NOW)

    def test_strict_fields_types_and_duplicate_json_keys(self) -> None:
        approval = self.token()
        for mutate in (
            lambda value: value.update(extra="not-allowed"),
            lambda value: value.update(version=True),
            lambda value: value.update(expires_at=True),
            lambda value: value.update(signature="z" * 64),
            lambda value: value.update(operator_id="Thomas"),
            lambda value: value.update(nonce="g" * 32),
            lambda value: value.update(nonce="a" * 31),
            lambda value: value.update(nonce="a" * 32),
        ):
            altered = dict(approval)
            mutate(altered)
            with self.subTest(altered=altered), self.assertRaises(OperatorApprovalError):
                verify_approval(KEY, altered, operation=OPERATION, plan_id=PLAN_ID,
                                plan_digest=PLAN_DIGEST, now=NOW)

        duplicate = json.dumps(approval, separators=(",", ":"))[:-1] + ",\"plan_id\":\"" + PLAN_ID + "\"}"
        with self.assertRaisesRegex(OperatorApprovalError, "operator_approval_invalid"):
            parse_approval(duplicate)
        with self.assertRaises(OperatorApprovalError):
            verify_approval(KEY, "{\"version\":NaN}", operation=OPERATION,
                            plan_id=PLAN_ID, plan_digest=PLAN_DIGEST, now=NOW)

    def test_key_file_loader_accepts_only_existing_private_regular_32_byte_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "operator.key"
            key_path.write_bytes(KEY)
            key_path.chmod(0o400)
            self.assertEqual(load_operator_key(str(key_path)), KEY)
            key_path.chmod(0o600)
            self.assertEqual(load_operator_key(str(key_path)), KEY)

            key_path.chmod(0o640)
            with self.assertRaises(OperatorApprovalError):
                load_operator_key(str(key_path))
            key_path.chmod(0o600)

            symlink_path = Path(directory) / "operator-symlink"
            symlink_path.symlink_to(key_path)
            with self.assertRaises(OperatorApprovalError):
                load_operator_key(str(symlink_path))

            fifo_path = Path(directory) / "operator-fifo"
            os.mkfifo(fifo_path, 0o600)
            with self.assertRaises(OperatorApprovalError):
                load_operator_key(str(fifo_path))

            hardlink_path = Path(directory) / "operator-hardlink"
            os.link(key_path, hardlink_path)
            with self.assertRaises(OperatorApprovalError):
                load_operator_key(str(key_path))

            key_path.unlink()
            hardlink_path.unlink()
            missing_path = Path(directory) / "does-not-exist"
            with self.assertRaises(OperatorApprovalError):
                load_operator_key(str(missing_path))
            self.assertFalse(missing_path.exists())
            with self.assertRaises(OperatorApprovalError):
                load_operator_key("relative/operator.key")

    def test_key_and_path_never_appear_in_errors_or_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            secret_path = Path(directory) / "sensitive-operator-key-name"
            secret_path.write_bytes(KEY)
            secret_path.chmod(0o644)
            try:
                load_operator_key(str(secret_path))
            except OperatorApprovalError as exc:
                rendered_error = str(exc)
            else:
                self.fail("unsafe key mode must be rejected")
            self.assertNotIn(str(secret_path), rendered_error)
            self.assertNotIn(KEY.hex(), rendered_error)

        token = self.token()
        rendered_token = json.dumps(token)
        self.assertNotIn(KEY.hex(), rendered_token)
        self.assertNotIn(OTHER_KEY.hex(), rendered_token)
        with self.assertRaises(OperatorApprovalError) as caught:
            verify_approval(OTHER_KEY, token, operation=OPERATION,
                            plan_id=PLAN_ID, plan_digest=PLAN_DIGEST, now=NOW)
        self.assertNotIn(KEY.hex(), str(caught.exception))
        self.assertNotIn(OTHER_KEY.hex(), str(caught.exception))


if __name__ == "__main__":
    unittest.main()
