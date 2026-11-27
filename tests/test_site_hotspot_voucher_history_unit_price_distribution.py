import unittest

from app.site_hotspot_voucher_history_unit_price_distribution import (
    VoucherUnitPriceDistributionError,
    project_voucher_unit_price_distribution,
)


def grid(rows):
    return {"totalRows": len(rows), "currentPage": 1, "currentSize": len(rows), "data": rows}


class VoucherUnitPriceDistributionTests(unittest.TestCase):
    def test_empty_and_filled_price_distribution_are_value_free(self):
        empty = project_voucher_unit_price_distribution(grid([]))
        filled = project_voucher_unit_price_distribution(grid([
            {"unitPrice": "private-price", "totalAmount": "private-total",
             "currency": "private-currency", "usedCount": 3}
        ]))
        self.assertEqual(empty["row_count"], 0)
        self.assertFalse(empty["partial"])
        self.assertEqual(filled["row_count"], 1)
        self.assertFalse(filled["partial"])
        self.assertTrue(all(filled["row_field_coverage"][field]["type_valid"] == 1
                            for field in ("unitPrice", "totalAmount", "currency", "usedCount")))
        rendered = repr(filled)
        self.assertTrue(all(secret not in rendered
                            for secret in ("private-price", "private-total", "private-currency")))


    def test_invalid_price_fields_are_counted_without_values(self):
        projected = project_voucher_unit_price_distribution(grid([
            {"unitPrice": 3, "totalAmount": None, "currency": "USD", "usedCount": True}
        ]))
        self.assertTrue(projected["partial"])
        self.assertEqual(projected["row_field_coverage"]["unitPrice"]["invalid"], 1)
        self.assertEqual(projected["row_field_coverage"]["totalAmount"]["null"], 1)
        self.assertEqual(projected["row_field_coverage"]["usedCount"]["invalid"], 1)


    def test_invalid_grid_is_partial_and_row_limit_is_rejected(self):
        malformed = project_voucher_unit_price_distribution({"data": {}})
        self.assertTrue(malformed["partial"])
        self.assertIsNone(malformed["row_count"])
        with self.assertRaises(VoucherUnitPriceDistributionError):
            project_voucher_unit_price_distribution(grid([{}] * 501))
