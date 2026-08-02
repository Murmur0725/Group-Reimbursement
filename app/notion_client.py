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
        return "".join(item.get("plain_text", "") for item in title_list)

    if prop_type == "number":
        return prop.get("number")

    if prop_type == "rich_text":
        text_list = prop.get("rich_text", [])
        return "".join(item.get("plain_text", "") for item in text_list)

    if prop_type == "select":
        select_obj = prop.get("select")
        return select_obj.get("name") if select_obj else None

    if prop_type == "status":
        status_obj = prop.get("status")
        return status_obj.get("name") if status_obj else None

    if prop_type == "people":
        people_list = prop.get("people", [])
        return ", ".join(person.get("name", "") for person in people_list if person.get("name"))

    if prop_type == "files":
        files = []
        for file_obj in prop.get("files", []):
            url = ""
            file_type = file_obj.get("type", "")

            if file_type == "file":
                url = file_obj.get("file", {}).get("url", "")
            elif file_type == "external":
                url = file_obj.get("external", {}).get("url", "")

            if url:
                files.append({
                    "url": url,
                    "id": file_obj.get("name", "unknown_id"),
                    "name": file_obj.get("name", "unknown"),
                    "type": file_type,
                })
        return files

    return None


def query_database_batches(settings, *, filter_by_status: bool = True):
    """Query Notion database using the official SDK (with retry on 429).

    When ``filter_by_status`` is True, only rows matching
    ``settings.status_to_process`` are returned.
    """
    notion = create_client(settings.notion_token)
    database_id = normalize_database_id(settings.notion_page_id)

    has_more = True
    next_cursor = None
    max_retries = 3
    backoff = 1.0

    while has_more:
        kwargs = {"database_id": database_id}
        if filter_by_status:
            kwargs["filter"] = {
                "property": settings.status_property_name,
                "select": {
                    "equals": settings.status_to_process,
                },
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


def query_all_database_batches(settings):
    """Query all Notion database rows without business filtering."""
    yield from query_database_batches(settings, filter_by_status=False)


def get_database_property_type(notion, database_id, property_name):
    """Return the Notion property type for a database property, if available."""
    database = notion.databases.retrieve(database_id=normalize_database_id(database_id))
    prop = database.get("properties", {}).get(property_name)
    return prop.get("type") if prop else None


def get_database_property_options(notion, database_id, property_name):
    """Return configured options for a select/status database property."""
    database = notion.databases.retrieve(database_id=normalize_database_id(database_id))
    prop = database.get("properties", {}).get(property_name)
    if not prop:
        return []

    prop_type = prop.get("type")
    if prop_type not in ("select", "status"):
        return []

    options = prop.get(prop_type, {}).get("options", [])
    return [
        {
            "name": option.get("name"),
            "id": option.get("id"),
            "color": option.get("color"),
        }
        for option in options
        if option.get("name")
    ]


def update_page_status(
    notion,
    page_id,
    status_property_name,
    status_processed,
    property_type="select",
):
    """Update a page's status property with retry on 429."""
    max_retries = 3
    backoff = 1.0
    notion_type = "status" if property_type == "status" else "select"

    for attempt in range(max_retries):
        try:
            notion.pages.update(
                page_id=page_id,
                properties={
                    status_property_name: {
                        notion_type: {
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
