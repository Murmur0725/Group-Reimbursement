import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import openpyxl

from app.invoice_to_delivery import default_delivery_excel_path
from app.main import _process_fapiao, interactive_menu


class InteractiveMenuTests(unittest.TestCase):
    def test_menu_returns_pdf_for_number_one(self):
        with patch("builtins.input", return_value="1"):
            result = interactive_menu()
        self.assertEqual(result, ["pdf"])

    def test_menu_returns_fapiao_by_name(self):
        with patch("builtins.input", return_value="fapiao"):
            result = interactive_menu()
        self.assertEqual(result, ["fapiao"])

    def test_menu_returns_clear_data_sentinel(self):
        with patch("builtins.input", return_value="clear-data"):
            result = interactive_menu()
        self.assertEqual(result, "__clear_data__")

    def test_menu_returns_none_for_quit(self):
        with patch("builtins.input", return_value="quit"):
            result = interactive_menu()
        self.assertIsNone(result)

    def test_menu_retries_on_invalid_input(self):
        with patch("builtins.input", side_effect=["invalid", "download"]):
            result = interactive_menu()
        self.assertEqual(result, ["download"])


class MainFapiaoTests(unittest.TestCase):
    def test_process_fapiao_generates_delivery_excel(self):
        """After saving fapiao PDFs, the delivery-order Excel is regenerated."""
        project_root = Path(__file__).resolve().parents[1]
        sample_pdf = next(
            p
            for p in (project_root / "data" / "fapiao").glob("*.pdf")
            if p.name != ".DS_Store"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            data_dir = base_dir / "data"
            fapiao_dir = data_dir / "fapiao"
            download_dir = base_dir / "downloads"
            fapiao_dir.mkdir(parents=True)
            download_dir.mkdir(parents=True)

            fake_pdf = download_dir / sample_pdf.name
            shutil.copy(sample_pdf, fake_pdf)

            settings = MagicMock()
            settings.data_dir = data_dir
            settings.fapiao_dir = fapiao_dir

            result = _process_fapiao(
                [{"type": "pdf", "path": fake_pdf}],
                settings,
                "page-id",
            )

            self.assertEqual(result, 1)
            self.assertTrue(any(fapiao_dir.glob("*.pdf")))
            expected_excel = default_delivery_excel_path(fapiao_dir)
            self.assertTrue(expected_excel.exists())

            workbook = openpyxl.load_workbook(expected_excel)
            worksheet = workbook.active
            receiver_col = None
            category_col = None
            for idx, cell in enumerate(worksheet[1]):
                if cell.value == "*收货人":
                    receiver_col = idx
                if cell.value == "*产品分类":
                    category_col = idx
            self.assertIsNotNone(receiver_col)
            self.assertIsNotNone(category_col)
            for row in worksheet.iter_rows(min_row=2, values_only=True):
                self.assertEqual(row[receiver_col], "mirna zordan")
                self.assertEqual(row[category_col], "实验耗材")

    def test_process_fapiao_removes_old_delivery_files(self):
        """When a new delivery-order Excel is generated, old ones are removed."""
        project_root = Path(__file__).resolve().parents[1]
        sample_pdf = next(
            p
            for p in (project_root / "data" / "fapiao").glob("*.pdf")
            if p.name != ".DS_Store"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            data_dir = base_dir / "data"
            fapiao_dir = data_dir / "fapiao"
            download_dir = base_dir / "downloads"
            fapiao_dir.mkdir(parents=True)
            download_dir.mkdir(parents=True)

            fake_pdf = download_dir / sample_pdf.name
            shutil.copy(sample_pdf, fake_pdf)

            # Create old generated delivery files that should be cleaned up.
            old_excel = fapiao_dir / "发票发货单整理_2026-06-22_11-29-31.xlsx"
            old_csv = fapiao_dir / "发票发货单整理_2026-06-22_11-45-08.csv"
            old_excel.write_bytes(b"fake excel")
            old_csv.write_text("课题号,商品名称\nY01656113,test")

            # An unrelated file should be left untouched.
            unrelated = fapiao_dir / "some_notes.txt"
            unrelated.write_text("keep me")

            settings = MagicMock()
            settings.data_dir = data_dir
            settings.fapiao_dir = fapiao_dir

            result = _process_fapiao(
                [{"type": "pdf", "path": fake_pdf}],
                settings,
                "page-id",
            )

            self.assertEqual(result, 1)
            self.assertFalse(old_excel.exists())
            self.assertFalse(old_csv.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue(any(fapiao_dir.glob("发票发货单整理_*.xlsx")))


if __name__ == "__main__":
    unittest.main()
