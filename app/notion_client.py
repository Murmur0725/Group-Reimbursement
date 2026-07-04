import logging
import time

import httpx
from notion_client import Client

logger = logging.getLogger(__name__)


def create_client(token):
    return Client(auth=token)


def normalize_database_id(database_id):
    if len(database_id) == 32 and "-" not in database_id:
        return (
            f"{database_id[:8]}-{database_id[8:12]}-"
            f"{database_id[12:16]}-{database_id[16:20]}-{database_id[20:]}"
        )
    return database_id


def ensure_database_access(notion, database_id):
    try:
        notion.databases.retrieve(database_id=normalize_database_id(database_id))
    except Exception as exc:
        if "Could not find database" in str(exc) or "404" in str(exc):
            raise RuntimeError(
                "\n[ERROR] Cannot find the database. This usually means the Integration "
                "is NOT connected.\n"
                "PLEASE FOLLOW THESE STEPS:\n"
                f"1. Open your Notion page: https://www.notion.so/{database_id}\n"
                "2. Click the '...' menu in top right -> 'Connect to'\n"
                "3. Select your integration (Auto PDF)\n"
                "--------------------------------------------------\n"
            ) from exc

        return f"[WARNING] Database check failed: {exc}. Continuing anyway..."

    return None


def extract_property_value(page, prop_name):
    props = page.get("properties", {})
    prop = props.get(prop_name)

    if not prop:
        return None

    prop_type = prop.get("type")

    if prop_type == "title":
        title_list = prop.get("title", [])
        return title_list[0].get("plain_text", "") if title_list else ""

    if prop_type == "number":
        return prop.get("number")

    if prop_type == "rich_text":
        text_list = prop.get("rich_text", [])
        return text_list[0].get("plain_text", "") if text_list else ""

    if prop_type == "select":
        select_obj = prop.get("select")
        return select_obj.get("name") if select_obj else None

    if prop_type == "people":
        people_list = prop.get("people", [])
        return people_list[0].get("name", "") if people_list else ""

    if prop_type == "files":
        files = []
        for file_obj in prop.get("files", []):
            url = ""

            if file_obj.get("type") == "file":
                url = file_obj.get("file", {}).get("url", "")
            elif file_obj.get("type") == "external":
                url = file_obj.get("external", {}).get("url", "")

            if url:
                files.append({
                    "url": url,
                    "id": file_obj.get("name", "unknown_id"),
                })
        return files

    return None


def query_database_batches(settings):
    """Query Notion database using the official SDK (with retry on 429)."""
    notion = create_client(settings.notion_token)
    database_id = normalize_database_id(settings.notion_page_id)

    has_more = True
    next_cursor = None
    max_retries = 3
    backoff = 1.0

    while has_more:
        filter_obj = {
            "property": settings.status_property_name,
            "select": {
                "equals": settings.status_to_process,
            },
        }

        kwargs = {
            "database_id": database_id,
            "filter": filter_obj,
        }
        if next_cursor:
            kwargs["start_cursor"] = next_cursor

        for attempt in range(max_retries):
            try:
                response = notion.databases.query(**kwargs)
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    wait = backoff * (2 ** attempt)
                    logger.warning(
                        "Notion API rate limited (429), retrying in %.1fs...", wait
                    )
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"Notion database query failed: {exc}") from exc
            except Exception:
                if attempt < max_retries - 1:
                    wait = backoff * (2 ** attempt)
                    logger.warning(
                        "Notion API error, retrying in %.1fs... (attempt %d/%d)",
                        wait, attempt + 1, max_retries,
                    )
                    time.sleep(wait)
                    continue
                raise

        yield response.get("results", [])
        has_more = response.get("has_more", False)
        next_cursor = response.get("next_cursor")


def update_page_status(notion, page_id, status_property_name, status_processed):
    """Update a page's status property with retry on 429."""
    max_retries = 3
    backoff = 1.0

    for attempt in range(max_retries):
        try:
            notion.pages.update(
                page_id=page_id,
                properties={
                    status_property_name: {
                        "select": {
                            "name": status_processed,
                        }
                    }
                },
            )
            return
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                wait = backoff * (2 ** attempt)
                logger.warning(
                    "Notion API rate limited (429) on status update, retrying in %.1fs...",
                    wait,
                )
                time.sleep(wait)
                continue
            raise
