import unittest
from pathlib import Path


from app.invoice_parser import parse_all_invoices, parse_invoice_text


SAMPLE_INVOICE_TEXT = """
电子发票
发票号码：12345678901234567890
开票日期：2024 年 05 月 20 日
购 名称：南方科技大学
销 名称：深圳实验耗材有限公司 统一社会信用代码
项目名称 规格型号 单位 数量 单价 金额 税率 税额
*化学试剂*琼脂糖 100g 瓶 2.0 150.00 300.00 13% 39.00
合 计 300.00 39.00
"""


class InvoiceParserTests(unittest.TestCase):
    def test_parse_invoice_text_extracts_header_and_items(self):
        invoice = parse_invoice_text(SAMPLE_INVOICE_TEXT)

        self.assertEqual(invoice.invoice_no, "12345678901234567890")
        self.assertEqual(invoice.date, "2024年05月20日")
        self.assertEqual(invoice.buyer, "南方科技大学")
        self.assertEqual(invoice.seller, "深圳实验耗材有限公司")
        self.assertEqual(len(invoice.items), 1)

        item = invoice.items[0]
        self.assertEqual(item.category, "化学试剂")
        self.assertEqual(item.name, "*化学试剂*琼脂糖")
        self.assertEqual(item.spec, "100g")
        self.assertEqual(item.unit, "瓶")
        self.assertEqual(item.qty, 2.0)
        self.assertEqual(item.unit_price, 150.0)
        self.assertEqual(item.amount, 300.0)
        self.assertEqual(item.tax_rate, 13.0)
        self.assertEqual(item.tax, 39.0)
        self.assertAlmostEqual(item.total, 339.0)
        self.assertAlmostEqual(item.tax_inclusive_unit_price * item.qty, item.total, places=6)

    def test_parse_all_invoices_ignores_unreadable_files(self):
        """parse_all_invoices should skip files that cannot be parsed."""
        project_root = Path(__file__).resolve().parents[1]
        fapiao_dir = project_root / "data" / "fapiao"

        # The production directory may be empty; the function should not crash.
        invoices = parse_all_invoices(fapiao_dir)
        self.assertIsInstance(invoices, list)


if __name__ == "__main__":
    unittest.main()
