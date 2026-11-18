import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.change_journal import ChangePlanJournal, derive_controller_binding
from app import journal_runtime


KEY = b"k" * 32
URL = "https://controller.example:8043"
CONTROLLER = "controller-opaque-id"


class JournalRuntimeTests(unittest.TestCase):
    def _init(self, path, *, key=KEY, persistent=True, url=URL, controller=CONTROLLER):
        return journal_runtime.initialize_journal_runtime(
            str(path), reference_key=key, reference_key_persistent=persistent,
            controller_url=url, controller_id=controller)

    def test_no_path_is_unconfigured_and_does_not_touch_filesystem(self):
        with tempfile.TemporaryDirectory() as parent:
            absent = Path(parent) / "must-not-exist"
            with patch.object(journal_runtime, "ChangePlanJournal") as open_journal:
                result = journal_runtime.initialize_journal_runtime(
                    None, reference_key=None, reference_key_persistent=False,
                    controller_url="bad", controller_id="bad")
            self.assertEqual(result.status, "unconfigured")
            self.assertIsNone(result.journal)
            self.assertIsNone(result.error_code)
            self.assertFalse(absent.exists())
            open_journal.assert_not_called()

    def test_configured_path_requires_persistent_32_byte_key_before_open(self):
        for key, persistent, expected in (
            (None, True, "reference_key_invalid"),
            (b"short", True, "reference_key_invalid"),
            (KEY, False, "reference_key_not_persistent"),
        ):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as root:
                with patch.object(journal_runtime, "ChangePlanJournal") as open_journal:
                    result = self._init(root, key=key, persistent=persistent)
                self.assertEqual(result.status, "unavailable")
                self.assertEqual(result.error_code, expected)
                open_journal.assert_not_called()
                self.assertEqual(list(Path(root).iterdir()), [])

    def test_invalid_binding_is_fixed_and_does_not_create_journal(self):
        with tempfile.TemporaryDirectory() as root:
            result = self._init(root, url="https://user:password@bad/path?secret=x")
            self.assertEqual(result.error_code, "journal_binding_invalid")
            self.assertNotIn(root, repr(result))
            self.assertNotIn("password", repr(result))
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_ready_opens_exactly_one_and_close_releases_exclusive_lock(self):
        with tempfile.TemporaryDirectory() as root:
            original = journal_runtime.ChangePlanJournal
            with patch.object(journal_runtime, "ChangePlanJournal", wraps=original) as opener:
                ready = self._init(root)
            self.assertTrue(ready.ready)
            self.assertEqual(opener.call_count, 1)
            other = self._init(root)
            self.assertEqual(other.error_code, "journal_locked")
            ready.close()
            reopened = self._init(root)
            self.assertTrue(reopened.ready)
            reopened.close()

    def test_key_or_controller_change_fails_binding_check_without_leaks(self):
        for key, url, controller in (
            (b"z" * 32, URL, CONTROLLER),
            (KEY, "https://other.example:8043", CONTROLLER),
            (KEY, URL, "different-controller"),
        ):
            with self.subTest(controller=controller, url=url), tempfile.TemporaryDirectory() as root:
                first = self._init(root)
                self.assertTrue(first.ready)
                first.journal.record_dispatch_intent(
                    operation="gateway-ipv6", plan_id="a" * 48,
                    target_refs={"site_ref": "b" * 24, "gateway_ref": "c" * 24},
                    before={"enable": False}, target={"enable": True})
                first.close()
                result = self._init(root, key=key, url=url, controller=controller)
                self.assertEqual(result.error_code, "journal_binding_mismatch")
                message = repr(result)
                for secret in (root, URL, CONTROLLER, KEY.hex(), b"z".hex()):
                    self.assertNotIn(secret, message)

    def test_corrupt_journal_returns_fixed_error(self):
        with tempfile.TemporaryDirectory() as root:
            journal = ChangePlanJournal(
                root, controller_binding=derive_controller_binding(KEY, URL, CONTROLLER))
            journal.close()
            (Path(root) / "change-plans.jsonl").write_bytes(b"{truncated")
            result = self._init(root)
            self.assertEqual(result.error_code, "journal_corrupt")
            self.assertNotIn(root, repr(result))

    def test_non_directory_path_returns_fixed_error_without_path_leak(self):
        with tempfile.TemporaryDirectory() as root:
            file_path = Path(root) / "not-a-directory-secret"
            file_path.write_text("x")
            result = self._init(file_path)
            self.assertEqual(result.status, "unavailable")
            self.assertIsNotNone(result.error_code)
            self.assertNotIn(str(file_path), repr(result))


if __name__ == "__main__":
    unittest.main()
