import os
import sys
import shutil
import subprocess
import importlib

load_dotenv = None
Client = None
download_media = None
create_pdf = None
httpx = None
notion = None

NOTION_TOKEN = None
NOTION_PAGE_ID = None
MODE = None
STATUS_PROPERTY_NAME = None
STATUS_TO_PROCESS = None
STATUS_PROCESSED = None
NUMBER_PROPERTY_NAME = None
NAME_PROPERTY_NAME = None
FILES_PROPERTY_NAME = None

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


def check_dependencies():
    """
    Check required runtime dependencies before importing application modules.
    """
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

    if os.path.exists(".venv/bin/python"):
        print("Install them with:")
        print("  uv pip install --python .venv/bin/python -r requirements.txt")
    else:
        print("Install them with:")
        print("  pip install -r requirements.txt")

    return False


def initialize_runtime():
    """
    Import third-party modules only after dependency checks pass.
    """
    global load_dotenv, Client, download_media, create_pdf, httpx, notion
    global NOTION_TOKEN, NOTION_PAGE_ID, MODE
    global STATUS_PROPERTY_NAME, STATUS_TO_PROCESS, STATUS_PROCESSED
    global NUMBER_PROPERTY_NAME, NAME_PROPERTY_NAME, FILES_PROPERTY_NAME

    from dotenv import load_dotenv as dotenv_load_dotenv
    from notion_client import Client as NotionClient
    from utils import download_media as media_downloader, create_pdf as pdf_creator
    import httpx as httpx_module

    load_dotenv = dotenv_load_dotenv
    Client = NotionClient
    download_media = media_downloader
    create_pdf = pdf_creator
    httpx = httpx_module

    load_dotenv()

    NOTION_TOKEN = os.getenv("NOTION_TOKEN")
    NOTION_PAGE_ID = os.getenv("NOTION_PAGE_ID")

    MODE = os.getenv("MODE", "pdf").lower()

    STATUS_PROPERTY_NAME = os.getenv("STATUS_PROPERTY_NAME", "状态")
    STATUS_TO_PROCESS = os.getenv("STATUS_TO_PROCESS", "1-发票+购买记录")
    STATUS_PROCESSED = os.getenv("STATUS_PROCESSED", "2-已处理")

    NUMBER_PROPERTY_NAME = os.getenv("NUMBER_PROPERTY_NAME", "编号")
    NAME_PROPERTY_NAME = os.getenv("NAME_PROPERTY_NAME", "名称")
    FILES_PROPERTY_NAME = os.getenv("FILES_PROPERTY_NAME", "文件和媒体")

    if not NOTION_TOKEN or not NOTION_PAGE_ID:
        print("Error: Please set NOTION_TOKEN and NOTION_PAGE_ID in .env file")
        return False

    notion = Client(auth=NOTION_TOKEN)
    return True


def get_property_value(page, prop_name):
    """
    Helper to extract value from a property object safely.
    """
    props = page.get("properties", {})
    prop = props.get(prop_name)

    if not prop:
        return None

    prop_type = prop.get("type")

    if prop_type == "title":
        title_list = prop.get("title", [])
        if title_list:
            return title_list[0].get("plain_text", "")
        return ""

    elif prop_type == "number":
        return prop.get("number")

    elif prop_type == "rich_text":
        text_list = prop.get("rich_text", [])
        if text_list:
            return text_list[0].get("plain_text", "")
        return ""

    elif prop_type == "select":
        select_obj = prop.get("select")
        if select_obj:
            return select_obj.get("name")
        return None

    elif prop_type == "files":
        files = []
        for file_obj in prop.get("files", []):
            url = ""
            if file_obj.get("type") == "file":
                url = file_obj.get("file", {}).get("url")
            elif file_obj.get("type") == "external":
                url = file_obj.get("external", {}).get("url")

            if url:
                files.append({
                    "url": url,
                    "id": file_obj.get("name", "unknown_id"),
                })
        return files

    return None


def main():
    if not check_dependencies():
        sys.exit(1)

    if not initialize_runtime():
        sys.exit(1)

    print("Starting Notion Media Processor...")

    try:
        try:
            check_id = NOTION_PAGE_ID
            if len(check_id) == 32:
                check_id = f"{check_id[:8]}-{check_id[8:12]}-{check_id[12:16]}-{check_id[16:20]}-{check_id[20:]}"

            notion.databases.retrieve(database_id=check_id)
        except Exception as e:
            if "Could not find database" in str(e) or "404" in str(e):
                print("\n[ERROR] Cannot find the database. This usually means the Integration is NOT connected.")
                print("PLEASE FOLLOW THESE STEPS:")
                print("1. Open your Notion page: https://www.notion.so/" + NOTION_PAGE_ID)
                print("2. Click the '...' menu in top right -> 'Connect to'")
                print("3. Select your integration (Auto PDF)")
                print("--------------------------------------------------\n")
                sys.exit(1)
            else:
                print(f"[WARNING] Database check failed: {e}. Continuing anyway...")

        print(f"Querying database {NOTION_PAGE_ID} for status '{STATUS_TO_PROCESS}'...")

        query_params = {
            "filter": {
                "property": STATUS_PROPERTY_NAME,
                "select": {
                    "equals": STATUS_TO_PROCESS
                }
            }
        }

        has_more = True
        next_cursor = None
        processed_count = 0

        while has_more:
            if next_cursor:
                query_params["start_cursor"] = next_cursor

            url = f"https://api.notion.com/v1/databases/{NOTION_PAGE_ID}/query"
            headers = {
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            }

            try:
                resp = httpx.post(url, headers=headers, json=query_params, timeout=30.0)
                resp.raise_for_status()
                response = resp.json()
            except Exception as e:
                print(f"Direct HTTP request failed: {e}")
                if hasattr(e, "response") and e.response is not None:
                    print(f"Response: {e.response.text}")
                raise e

            results = response.get("results", [])
            has_more = response.get("has_more")
            next_cursor = response.get("next_cursor")

            print(f"Found {len(results)} items to process in this batch.")

            for page in results:
                page_id = page["id"]

                number = get_property_value(page, NUMBER_PROPERTY_NAME)
                name = get_property_value(page, NAME_PROPERTY_NAME)
                files = get_property_value(page, FILES_PROPERTY_NAME)

                if number is None:
                    number = "NoNum"
                if not name:
                    name = "NoName"

                print(f"Processing: [{number}] {name} ({len(files) if files else 0} files)")

                if not files:
                    print(f"  No files found for {name}, skipping download.")
                    continue

                downloaded_items = download_media(files)

                if not downloaded_items:
                    print("  Failed to download any valid media.")
                    continue

                if MODE == "download":
                    print("  Download completed. Skipping PDF generation and status update (MODE=download).")
                    processed_count += 1
                    continue

                pdf_filename = f"{number}_{name}.pdf"
                pdf_filename = "".join(
                    [c for c in pdf_filename if c.isalnum() or c in (" ", ".", "_", "-")]
                ).strip()

                output_dir = os.path.join(os.getcwd(), "output_pdfs")
                os.makedirs(output_dir, exist_ok=True)

                output_path = os.path.join(output_dir, pdf_filename)

                create_pdf(downloaded_items, output_path, label_text=number)
                print(f"  Generated PDF: {output_path}")

                for item in downloaded_items:
                    try:
                        os.remove(item["path"])
                    except Exception as e:
                        print(f"  Warning: Could not remove temp file {item['path']}: {e}")

                print("  [WARNING] Notion API limitations prevent uploading local files.")
                print("            The PDF has been saved locally.")

                try:
                    print(f"  Updating status to '{STATUS_PROCESSED}'...")
                    notion.pages.update(
                        page_id=page_id,
                        properties={
                            STATUS_PROPERTY_NAME: {
                                "select": {
                                    "name": STATUS_PROCESSED
                                }
                            }
                        }
                    )
                    print("  Status updated successfully.")
                    processed_count += 1
                except Exception as e:
                    print(f"  Error updating status: {e}")

        print(f"\nProcessing complete. {processed_count} items processed.")

        if processed_count > 0:
            print("\nOpening output folder...")
            output_dir = os.path.join(os.getcwd(), "output_pdfs")
            if os.path.exists(output_dir):
                subprocess.run(["open", output_dir])

    except Exception as e:
        print(f"An error occurred: {e}")


def cleanup_downloads():
    targets = ["downloads", "output_pdfs"]
    removed_any = False
    for d in targets:
        path = os.path.join(os.getcwd(), d)
        if os.path.exists(path):
            shutil.rmtree(path)
            print(f"Removed {path}")
            removed_any = True
    if not removed_any:
        print("No downloads or output_pdfs directory to remove.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        first = sys.argv[1].lower()
        combined = " ".join(sys.argv[1:]).lower()
        normalized = combined.replace(" ", "")
        if first in ("clear", "cleanup", "clearup") or normalized in ("clear", "cleanup", "clearup"):
            cleanup_downloads()
        else:
            main()
    else:
        main()
