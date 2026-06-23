import unittest
from pathlib import Path

from app.invoice_parser import parse_all_invoices


class InvoiceParserTests(unittest.TestCase):
    def test_parse_sample_invoices(self):
        """All sample invoices in data/fapiao should parse without errors."""
        project_root = Path(__file__).resolve().parents[1]
        fapiao_dir = project_root / "data" / "fapiao"

        invoices = parse_all_invoices(fapiao_dir)
        self.assertGreater(len(invoices), 0)

        for invoice in invoices:
            self.assertIsNotNone(invoice.invoice_no)
            self.assertEqual(invoice.buyer, "南方科技大学")
            self.assertIsNotNone(invoice.seller)
            self.assertTrue(len(invoice.items) > 0)

            for item in invoice.items:
                self.assertTrue(item.category)
                self.assertTrue(item.name.startswith(f"*{item.category}*"))
                self.assertTrue(item.unit)
                self.assertGreater(item.qty, 0)
                self.assertGreater(item.unit_price, 0)
                self.assertGreater(item.amount, 0)
                # Ensure the tax-inclusive unit price is consistent.
                self.assertAlmostEqual(
                    item.tax_inclusive_unit_price * item.qty,
                    item.total,
                    places=6,
                )


if __name__ == "__main__":
    unittest.main()
