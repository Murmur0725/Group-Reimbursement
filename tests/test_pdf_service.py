import tempfile
import unittest
from pathlib import Path

from app.pdf_service import is_pdf_file


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
