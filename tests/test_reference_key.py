from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.reference_key import KEY_BYTES, ReferenceKeyError, load_reference_key


class ReferenceKeyTests(unittest.TestCase):
    def test_loads_private_regular_exact_length_key_without_changing_it(self) -> None:
        secret = b"s" * KEY_BYTES
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "key"
            key_path.write_bytes(secret)
            key_path.chmod(0o600)
            self.assertEqual(load_reference_key(key_path), secret)
            self.assertEqual(key_path.read_bytes(), secret)
            self.assertEqual(key_path.stat().st_mode & 0o777, 0o600)
            key_path.chmod(0o400)
            self.assertEqual(load_reference_key(key_path), secret)

    def test_rejects_missing_key_in_stable_mode_without_ephemeral_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "does-not-exist"
            with patch("app.reference_key.secrets.token_bytes") as generate:
                with self.assertRaises(ReferenceKeyError) as caught:
                    load_reference_key(missing)
            generate.assert_not_called()
            self.assertEqual(caught.exception.code, "reference_key_file_unavailable")
            self.assertNotIn(str(missing), str(caught.exception))

    def test_requires_explicit_ephemeral_mode_when_path_is_absent(self) -> None:
        with patch("app.reference_key.secrets.token_bytes", return_value=b"e" * KEY_BYTES) as generate:
            with self.assertRaises(ReferenceKeyError) as caught:
                load_reference_key()
            self.assertEqual(caught.exception.code, "reference_key_unconfigured")
            generate.assert_not_called()
            self.assertEqual(load_reference_key(ephemeral=True), b"e" * KEY_BYTES)
            generate.assert_called_once_with(KEY_BYTES)

    def test_rejects_ambiguous_and_invalid_paths(self) -> None:
        for path in ("", 42):
            with self.subTest(path_type=type(path).__name__), self.assertRaises(ReferenceKeyError) as caught:
                load_reference_key(path)  # type: ignore[arg-type]
            self.assertEqual(caught.exception.code, "reference_key_path_invalid")
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "key"
            key_path.write_bytes(b"k" * KEY_BYTES)
            key_path.chmod(0o600)
            with self.assertRaises(ReferenceKeyError) as caught:
                load_reference_key(key_path, ephemeral=True)
            self.assertEqual(caught.exception.code, "reference_key_configuration_invalid")

    def test_rejects_symlinks_and_non_regular_files_without_leaking_path_or_key(self) -> None:
        secret = b"private-key-material-1234567890"[:KEY_BYTES]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.write_bytes(secret)
            target.chmod(0o600)
            link = root / "link"
            link.symlink_to(target)
            for unsafe in (link, root):
                with self.subTest(entry=unsafe.name), self.assertRaises(ReferenceKeyError) as caught:
                    load_reference_key(unsafe)
                self.assertEqual(caught.exception.code, "reference_key_file_unavailable"
                                 if unsafe == link else "reference_key_file_invalid")
                self.assertNotIn(str(unsafe), str(caught.exception))
                self.assertNotIn(secret.decode(), str(caught.exception))

    @unittest.skipUnless(hasattr(os, "mkfifo") and hasattr(os, "O_NONBLOCK"),
                         "FIFO nonblocking flags are unavailable")
    def test_fifo_without_writer_fails_promptly_before_reading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory) / "key-pipe"
            os.mkfifo(fifo, 0o600)
            started = time.monotonic()
            with patch("app.reference_key.os.fdopen") as fdopen:
                with self.assertRaises(ReferenceKeyError) as caught:
                    load_reference_key(fifo)
            elapsed = time.monotonic() - started
            self.assertEqual(caught.exception.code, "reference_key_file_invalid")
            self.assertLess(elapsed, 1.0)
            fdopen.assert_not_called()

    def test_rejects_wrong_lengths_and_group_or_world_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (("short", b"s" * (KEY_BYTES - 1)),
                                ("long", b"l" * (KEY_BYTES + 1))):
                path = root / name
                path.write_bytes(value)
                path.chmod(0o600)
                with self.subTest(name=name), self.assertRaises(ReferenceKeyError) as caught:
                    load_reference_key(path)
                self.assertEqual(caught.exception.code, "reference_key_file_invalid")

            exposed = root / "exposed"
            exposed.write_bytes(b"x" * KEY_BYTES)
            for mode in (0o640, 0o700):
                exposed.chmod(mode)
                with self.subTest(mode=oct(mode)), self.assertRaises(ReferenceKeyError) as caught:
                    load_reference_key(exposed)
                self.assertEqual(caught.exception.code, "reference_key_permissions_invalid")
                self.assertNotIn("x" * KEY_BYTES, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
