import httpx
from notion_client import Client


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
    has_more = True
    next_cursor = None

    while has_more:
        query_params = {
            "filter": {
                "property": settings.status_property_name,
                "select": {
                    "equals": settings.status_to_process,
                },
            }
        }

        if next_cursor:
            query_params["start_cursor"] = next_cursor

        url = f"https://api.notion.com/v1/databases/{settings.notion_page_id}/query"
        headers = {
            "Authorization": f"Bearer {settings.notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        try:
            response = httpx.post(url, headers=headers, json=query_params, timeout=30.0)
            response.raise_for_status()
        except Exception as exc:
            message = f"Direct HTTP request failed: {exc}"
            if hasattr(exc, "response") and exc.response is not None:
                message += f"\nResponse: {exc.response.text}"
            raise RuntimeError(message) from exc

        payload = response.json()
        yield payload.get("results", [])
        has_more = payload.get("has_more", False)
        next_cursor = payload.get("next_cursor")


def update_page_status(notion, page_id, status_property_name, status_processed):
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
