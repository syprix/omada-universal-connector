"""Opt-in initialization for the durable change-plan journal."""
from __future__ import annotations

from dataclasses import dataclass

try:
    from .change_journal import ChangeJournalError, ChangePlanJournal, derive_controller_binding
except ImportError:  # direct-module imports used by some local scripts
    from change_journal import ChangeJournalError, ChangePlanJournal, derive_controller_binding


_SAFE_CODES = frozenset({
    "journal_binding_invalid", "journal_binding_mismatch", "journal_corrupt",
    "journal_directory_sync_failed", "journal_directory_unavailable", "journal_file_unsafe",
    "journal_file_unavailable", "journal_full", "journal_locked", "journal_path_invalid",
    "journal_permissions_invalid", "journal_record_too_large", "journal_schema_invalid",
    "journal_unavailable", "journal_write_failed", "plan_id_invalid",
    "reference_key_invalid", "reference_key_not_persistent",
})


@dataclass
class JournalRuntime:
    """Initialization result; callers own and must close a ready journal."""

    status: str
    journal: ChangePlanJournal | None = None
    error_code: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "ready" and self.journal is not None and self.journal.available

    def close(self) -> None:
        if self.journal is not None:
            self.journal.close()
            self.journal = None
            self.status = "closed"


def initialize_journal_runtime(
    directory: str | None,
    *,
    reference_key: bytes | None,
    reference_key_persistent: bool,
    controller_url: str,
    controller_id: str,
) -> JournalRuntime:
    """Open one journal using the already-loaded persistent reference key.

    No path is touched when ``directory`` is ``None``. The helper never loads
    or creates keys, and deliberately returns fixed error codes without paths
    or controller data.
    """
    if directory is None:
        return JournalRuntime("unconfigured")
    if not isinstance(directory, str) or not directory:
        return JournalRuntime("unavailable", error_code="journal_path_invalid")
    if reference_key_persistent is not True:
        return JournalRuntime("unavailable", error_code="reference_key_not_persistent")
    if not isinstance(reference_key, bytes) or len(reference_key) != 32:
        return JournalRuntime("unavailable", error_code="reference_key_invalid")
    try:
        binding = derive_controller_binding(reference_key, controller_url, controller_id)
        journal = ChangePlanJournal(directory, controller_binding=binding)
    except ChangeJournalError as exc:
        code = exc.code if exc.code in _SAFE_CODES else "journal_unavailable"
        return JournalRuntime("unavailable", error_code=code)
    except (OSError, TypeError, ValueError):
        return JournalRuntime("unavailable", error_code="journal_unavailable")
    return JournalRuntime("ready", journal=journal)
