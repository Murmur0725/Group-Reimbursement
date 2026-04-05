import os
import unittest
from unittest.mock import patch

from app.config import load_settings


class ConfigTests(unittest.TestCase):
    def test_load_settings_reads_env(self):
        with patch.dict(
            os.environ,
            {
                "NOTION_TOKEN": "token",
                "NOTION_PAGE_ID": "page-id",
                "MODE": "download",
                "STATUS_PROPERTY_NAME": "状态",
                "STATUS_TO_PROCESS": "待处理",
                "STATUS_PROCESSED": "已处理",
                "NUMBER_PROPERTY_NAME": "编号",
                "NAME_PROPERTY_NAME": "名称",
                "FILES_PROPERTY_NAME": "文件和媒体",
            },
            clear=True,
        ):
            settings = load_settings()

        self.assertEqual(settings.notion_token, "token")
        self.assertEqual(settings.notion_page_id, "page-id")
        self.assertEqual(settings.mode, "download")


if __name__ == "__main__":
    unittest.main()
