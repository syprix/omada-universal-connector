"""Load a connector reference HMAC key without persisting or exposing it."""

from __future__ import annotations

import os
import secrets
import stat


KEY_BYTES = 32


class ReferenceKeyError(ValueError):
    """A fixed, non-sensitive reference-key configuration error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def load_reference_key(
    path: str | os.PathLike[str] | None = None,
    *,
    ephemeral: bool = False,
) -> bytes:
    """Load an exactly 32-byte private key, or explicitly use an ephemeral key.

    The stable mode requires a regular file that is not group/world accessible.
    The function never creates or writes a key file and never includes a path or
    key material in errors. With no path, callers must explicitly opt into the
    legacy ephemeral mode; stable mode never falls back to a generated key.
    """
    if path is None:
        if ephemeral:
            return secrets.token_bytes(KEY_BYTES)
        raise ReferenceKeyError("reference_key_unconfigured")
    if ephemeral:
        raise ReferenceKeyError("reference_key_configuration_invalid")

    try:
        path_text = os.fspath(path)
    except TypeError:
        raise ReferenceKeyError("reference_key_path_invalid") from None
    if not isinstance(path_text, str) or not path_text:
        raise ReferenceKeyError("reference_key_path_invalid")

    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ReferenceKeyError("reference_key_platform_unsupported")
    flags = (os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NONBLOCK", 0))
    try:
        fd = os.open(path_text, flags)
    except OSError:
        raise ReferenceKeyError("reference_key_file_unavailable") from None

    try:
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size != KEY_BYTES:
                raise ReferenceKeyError("reference_key_file_invalid")
            if stat.S_IMODE(info.st_mode) not in {0o400, 0o600}:
                raise ReferenceKeyError("reference_key_permissions_invalid")
            with os.fdopen(fd, "rb", closefd=False) as handle:
                value = handle.read(KEY_BYTES + 1)
            if len(value) != KEY_BYTES:
                raise ReferenceKeyError("reference_key_file_invalid")
            return value
        except ReferenceKeyError:
            raise
        except OSError:
            raise ReferenceKeyError("reference_key_read_failed") from None
    finally:
        os.close(fd)
