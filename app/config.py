import importlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DOWNLOAD_DIR = DATA_DIR / "downloads"
OUTPUT_DIR = DATA_DIR / "output_pdfs"
FAPIAO_DIR = DATA_DIR / "fapiao"

REQUIRED_DEPENDENCIES = {
    "dotenv": "python-dotenv",
    "notion_client": "notion-client",
    "PIL": "pillow",
    "reportlab": "reportlab",
    "pypdf": "pypdf",
    "cryptography": "cryptography",
    "httpx": "httpx",
}

VALID_MODES = {"pdf", "download", "fapiao"}

# Notion page IDs are 32 hex characters, optionally hyphenated as UUIDv4.
_NOTION_ID_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
_NOTION_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


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
    amount_property_name: str
    applicant_property_name: str
    reimburse_to_property_name: str
    remark_property_name: str
    files_property_name: str
    base_dir: Path = BASE_DIR
    data_dir: Path = DATA_DIR
    download_dir: Path = DOWNLOAD_DIR
    output_dir: Path = OUTPUT_DIR
    fapiao_dir: Path = FAPIAO_DIR
    # Collected validation warnings that are not fatal.
    warnings: list[str] = field(default_factory=list)

    def validate(self) -> "Settings":
        """Validate this settings instance and return it (with warnings appended)."""
        warnings: list[str] = []

        if self.mode not in VALID_MODES:
            raise ValueError(
                f"Invalid MODE '{self.mode}'. Must be one of: {', '.join(sorted(VALID_MODES))}"
            )

        if not _NOTION_ID_RE.match(self.notion_page_id) and not _NOTION_UUID_RE.match(
            self.notion_page_id
        ):
            warnings.append(
                f"NOTION_PAGE_ID '{self.notion_page_id}' does not look like "
                "a valid Notion database ID (expected 32 hex chars or UUID)."
            )

        if self.mode == "fapiao" and not self.fapiao_dir.exists():
            warnings.append(
                f"FAPIAO_DIR '{self.fapiao_dir}' does not exist yet — it will be created."
            )

        # Return a new instance with warnings baked in (frozen dataclass).
        object.__setattr__(self, "warnings", warnings)
        return self


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
    # Log and print — this runs before logging setup, so we use both.
    msg = f"Missing Python dependencies: {packages}"
    logger.error(msg)
    print(f"[ERROR] {msg}")
    print("Install them with:")
    print("  uv sync")

    return False


def init_config():
    """Load environment variables from the project root .env file.

    This should be called once at application entry points before
    ``load_settings()`` is used.
    """
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env", override=True)


def load_settings(mode_override=None):
    notion_token = os.getenv("NOTION_TOKEN")
    notion_page_id = os.getenv("NOTION_PAGE_ID")

    if not notion_token or not notion_page_id:
        raise ValueError("Please set NOTION_TOKEN and NOTION_PAGE_ID in .env file")

    mode = (mode_override or os.getenv("MODE", "pdf")).lower()
    status_to_process_default = os.getenv("STATUS_TO_PROCESS", "1-发票+购买记录")
    status_to_process = os.getenv(
        f"STATUS_TO_PROCESS_{mode.upper()}",
        status_to_process_default,
    )

    return Settings(
        notion_token=notion_token,
        notion_page_id=notion_page_id,
        mode=mode,
        status_property_name=os.getenv("STATUS_PROPERTY_NAME", "状态"),
        status_to_process=status_to_process,
        status_processed=os.getenv("STATUS_PROCESSED", "2-已处理"),
        number_property_name=os.getenv("NUMBER_PROPERTY_NAME", "编号"),
        name_property_name=os.getenv("NAME_PROPERTY_NAME", "名称"),
        amount_property_name=os.getenv("AMOUNT_PROPERTY_NAME", "金额"),
        applicant_property_name=os.getenv("APPLICANT_PROPERTY_NAME", "申请人"),
        reimburse_to_property_name=os.getenv("REIMBURSE_TO_PROPERTY_NAME", "报销给谁"),
        remark_property_name=os.getenv("REMARK_PROPERTY_NAME", "备注"),
        files_property_name=os.getenv("FILES_PROPERTY_NAME", "文件和媒体"),
        fapiao_dir=Path(os.getenv("FAPIAO_DIR", str(FAPIAO_DIR))),
    ).validate()


def ensure_data_directories(settings):
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.fapiao_dir.mkdir(parents=True, exist_ok=True)
