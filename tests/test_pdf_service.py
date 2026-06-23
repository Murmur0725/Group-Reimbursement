import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.pdf_service import is_pdf_file, merge_pdfs


def _create_test_pdf(path: Path, text: str, pages: int = 1) -> None:
    """Create a simple PDF with the given text on each page."""
    pdf_canvas = canvas.Canvas(str(path))
    for idx in range(pages):
        pdf_canvas.drawString(100, 700, f"{text} page {idx + 1}")
        pdf_canvas.showPage()
    pdf_canvas.save()


class MergePdfsTests(unittest.TestCase):
    def test_merge_pdfs_combines_multiple_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            first = tmp_path / "first.pdf"
            second = tmp_path / "second.pdf"
            _create_test_pdf(first, "first", pages=2)
            _create_test_pdf(second, "second", pages=3)

            merged = tmp_path / "merged.pdf"
            merge_pdfs([first, second], merged)

            reader = PdfReader(str(merged))
            self.assertEqual(len(reader.pages), 5)

    def test_merge_pdfs_creates_empty_pdf_for_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            merged = Path(tmp_dir) / "merged.pdf"
            merge_pdfs([], merged)

            self.assertTrue(merged.exists())
            reader = PdfReader(str(merged))
            self.assertEqual(len(reader.pages), 0)


class PdfServiceTests(unittest.TestCase):
    def test_is_pdf_file_detects_pdf_header(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")

            self.assertTrue(is_pdf_file(pdf_path))

    def test_is_pdf_file_rejects_non_pdf(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            text_path = Path(tmp_dir) / "sample.txt"
            text_path.write_text("hello")

            self.assertFalse(is_pdf_file(text_path))


if __name__ == "__main__":
    unittest.main()
