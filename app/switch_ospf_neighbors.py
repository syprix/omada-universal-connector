"""Compact, redacted summary of a switch OSPF neighbor table."""
from __future__ import annotations

import re


class SwitchOspfNeighborsError(ValueError):
    """Input exceeds the bounded neighbor summary contract."""


_STATE = re.compile(r"[A-Za-z0-9_.-]{1,32}")
_MAX_ROWS = 10_000
_MAX_STATES = 64


def summarize_switch_ospf_neighbors(rows: object) -> dict[str, object]:
    if not isinstance(rows, list) or len(rows) > _MAX_ROWS:
        raise SwitchOspfNeighborsError()
    by_state: dict[str, int] = {}
    unknown_state_rows = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 32:
            unknown_state_rows += 1
            continue
        state = row.get("state")
        if not isinstance(state, str) or not _STATE.fullmatch(state):
            unknown_state_rows += 1
            continue
        if state not in by_state and len(by_state) >= _MAX_STATES:
            unknown_state_rows += 1
            continue
        by_state[state] = by_state.get(state, 0) + 1
    return {"status": "ok", "resource": "switch_ospf_neighbors",
            "count": len(rows), "summary": {"by_state": by_state,
                                              "unknown_state_rows": unknown_state_rows},
            "partial": unknown_state_rows > 0}
