import importlib
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DOWNLOAD_DIR = DATA_DIR / "downloads"
OUTPUT_DIR = DATA_DIR / "output_pdfs"

REQUIRED_DEPENDENCIES = {
    "dotenv": "python-dotenv",
    "notion_client": "notion-client",
    "requests": "requests",
    "PIL": "pillow",
    "reportlab": "reportlab",
    "pypdf": "pypdf",
    "cryptography": "cryptography",
    "httpx": "httpx",
}


@dataclass(frozen=True)
class Settings:
    notion_token: str
    notion_page_id: str
    mode: str
    status_property_name: str
    status_to_process: str
    status_processed: str
    number_property_name: str
    name_property_name: str
    files_property_name: str
    base_dir: Path = BASE_DIR
    data_dir: Path = DATA_DIR
    download_dir: Path = DOWNLOAD_DIR
    output_dir: Path = OUTPUT_DIR


def check_dependencies():
    missing_packages = []

    for module_name, package_name in REQUIRED_DEPENDENCIES.items():
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            missing_packages.append(package_name)

    if not missing_packages:
        return True

    packages = ", ".join(sorted(set(missing_packages)))
    print("[ERROR] Missing Python dependencies:", packages)
    print("Install them with:")
    print("  uv sync")

    return False


def load_settings():
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")

    notion_token = os.getenv("NOTION_TOKEN")
    notion_page_id = os.getenv("NOTION_PAGE_ID")

    if not notion_token or not notion_page_id:
        raise ValueError("Please set NOTION_TOKEN and NOTION_PAGE_ID in .env file")

    return Settings(
        notion_token=notion_token,
        notion_page_id=notion_page_id,
        mode=os.getenv("MODE", "pdf").lower(),
        status_property_name=os.getenv("STATUS_PROPERTY_NAME", "状态"),
        status_to_process=os.getenv("STATUS_TO_PROCESS", "1-发票+购买记录"),
        status_processed=os.getenv("STATUS_PROCESSED", "2-已处理"),
        number_property_name=os.getenv("NUMBER_PROPERTY_NAME", "编号"),
        name_property_name=os.getenv("NAME_PROPERTY_NAME", "名称"),
        files_property_name=os.getenv("FILES_PROPERTY_NAME", "文件和媒体"),
    )


def ensure_data_directories(settings):
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
