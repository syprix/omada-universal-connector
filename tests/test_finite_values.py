from __future__ import annotations

import math
import unittest

from app.finite_values import is_finite_number


class FiniteNumberTests(unittest.TestCase):
    def test_accepts_finite_builtin_numbers(self) -> None:
        for value in (0, -1, 10**100, 0.0, -12.5, 1e308):
            with self.subTest(value=value):
                self.assertTrue(is_finite_number(value))

    def test_rejects_nonfinite_values(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                self.assertFalse(is_finite_number(value))

    def test_rejects_bool_strings_none_and_overflowing_integer(self) -> None:
        for value in (True, False, "1", "NaN", None, 10**400):
            with self.subTest(value=type(value).__name__):
                self.assertFalse(is_finite_number(value))


if __name__ == "__main__":
    unittest.main()
