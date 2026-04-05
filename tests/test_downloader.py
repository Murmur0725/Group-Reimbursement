import tempfile
import unittest
from pathlib import Path

from app.downloader import resolve_download_path, sanitize_filename


class DownloaderTests(unittest.TestCase):
    def test_sanitize_filename_keeps_supported_characters(self):
        self.assertEqual(sanitize_filename("发票:/test?.pdf"), "发票test.pdf")

    def test_resolve_download_path_avoids_collisions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            first_path = resolve_download_path(directory, "64.pdf", "64.pdf")
            first_path.touch()
            second_path = resolve_download_path(directory, "64.pdf", "64.pdf")

        self.assertNotEqual(first_path, second_path)
        self.assertTrue(str(second_path.name).startswith("64.pdf_64"))


if __name__ == "__main__":
    unittest.main()
