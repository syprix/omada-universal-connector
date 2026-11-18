"""Small fail-closed numeric validation helpers."""
from __future__ import annotations

import math


def is_finite_number(value: object) -> bool:
    """Accept only builtin finite ints/floats; reject bool and unsafe coercions."""
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError):
        return False
