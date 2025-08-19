import os
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
PAGE_ID = os.getenv("NOTION_PAGE_ID")
NOTION_VERSION = "2022-06-28"



BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

DONE_DB_ID = os.getenv("NOTION_DONE_DB_ID")
DAILY_COMP_DB_ID = os.getenv("NOTION_DAILY_COMP_DB_ID")

def notion_today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()

def search_database_by_title(title: str) -> Optional[str]:
    """Use Notion search API to find a database by its title (exact match, case-insensitive)."""
    url = f"{BASE}/search"
    payload = {
        "query": title,
        "filter": {"value": "database", "property": "object"},
        "page_size": 25,
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    if not resp.ok:
        raise SystemExit(f"❌ Notion search failed for '{title}': {resp.status_code} {resp.text}")
    data = resp.json().get("results", [])
    for item in data:
        db_title = ""
        try:
            db_title = "".join([t.get("plain_text","") for t in item["title"]]).strip()
        except Exception:
            pass
        if db_title.lower() == title.lower():
            return item["id"]
    return None

def ensure_done_db_id() -> Optional[str]:
    global DONE_DB_ID
    if DONE_DB_ID:
        return DONE_DB_ID
    DID = search_database_by_title("Done")
    DONE_DB_ID = DID
    return DID

def ensure_daily_comp_db_id() -> Optional[str]:
    global DAILY_COMP_DB_ID
    if DAILY_COMP_DB_ID:
        return DAILY_COMP_DB_ID
    DID = search_database_by_title("Daily Completion")
    DAILY_COMP_DB_ID = DID
    return DID

def create_page_in_db(db_id: str, properties: Dict) -> None:
    url = f"{BASE}/pages"
    payload = {
        "parent": {"type": "database_id", "database_id": db_id},
        "properties": properties
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    if not resp.ok:
        raise SystemExit(f"❌ Failed to create page in DB {db_id}: {resp.status_code} {resp.text}")

def log_done_item(task_text: str) -> None:
    dbid = ensure_done_db_id()
    if not dbid:
        return  # silently skip if DB not found
    props = {
        "Name": {"title": [{"type": "text", "text": {"content": task_text or "Task"}}]},
        "Date": {"date": {"start": notion_today_iso()}}
    }
    create_page_in_db(dbid, props)

def log_daily_completion(completed: int, total: int) -> None:
    dbid = ensure_daily_comp_db_id()
    if not dbid:
        return
    state = f"{completed}/{total}"
    props = {
        "State": {"title": [{"type": "text", "text": {"content": state}}]},
        "Date": {"date": {"start": notion_today_iso()}}
    }
    create_page_in_db(dbid, props)

def set_todo_checked(block_id: str, checked: bool) -> None:
    url = f"{BASE}/blocks/{block_id}"
    payload = {"to_do": {"checked": checked}}
    resp = requests.patch(url, headers=HEADERS, json=payload)
    if not resp.ok:
        raise SystemExit(f"❌ Failed to update checkbox {block_id}: {resp.status_code} {resp.text}")

def get_page(page_id: str) -> Dict:
    """Fetch a page object to verify access (404 also means the integration is not invited)."""
    url = f"{BASE}/pages/{page_id}"
    resp = requests.get(url, headers=HEADERS)
    if not resp.ok:
        # Bubble up useful context for troubleshooting
        raise SystemExit(f"❌ Notion API error on GET /pages/{page_id}: {resp.status_code} {resp.text}")
    return resp.json()

def get_all_children(parent_block_id: str) -> List[Dict]:
    """Fetch all direct children blocks of a page."""
    url = f"{BASE}/blocks/{parent_block_id}/children"
    results: List[Dict] = []
    start_cursor = None
    while True:
        params = {}
        if start_cursor:
            params["start_cursor"] = start_cursor
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))
        if data.get("has_more"):
            start_cursor = data.get("next_cursor")
        else:
            break
    return results

def rich_text_to_plain(block: Dict) -> str:
    """Extract plain text from a block rich_text field."""
    t = block.get("type")
    if t in ("heading_1", "heading_2", "heading_3", "paragraph"):
        rich = block[t].get("rich_text", [])
    elif t == "to_do":
        rich = block["to_do"].get("rich_text", [])
    else:
        return ""
    return "".join([span.get("plain_text", "") for span in rich]).strip()

def is_empty_paragraph(block: Dict) -> bool:
    """True if block is an empty paragraph (used to join checkbox lists visually)."""
    if block.get("type") != "paragraph":
        return False
    rich = block["paragraph"].get("rich_text", [])
    text = "".join([span.get("plain_text", "") for span in rich]).strip()
    return text == ""

def is_header_with_text(block: Dict, targets: List[str]) -> bool:
    """Check if block is a header/paragraph with target text (case-insensitive)."""
    t = block.get("type")
    if t not in ("heading_1", "heading_2", "heading_3", "paragraph"):
        return False
    text = rich_text_to_plain(block).rstrip(":").strip().lower()
    targets_lc = [s.lower() for s in targets]
    return any(text.startswith(t) for t in targets_lc)

def append_blocks_after(parent_id: str, after_block_id: str, new_blocks: List[Dict]) -> None:
    """Insert new children into parent right after the given existing child block."""
    url = f"{BASE}/blocks/{parent_id}/children"
    payload = {"children": new_blocks, "after": after_block_id}
    resp = requests.patch(url, headers=HEADERS, json=payload)
    if not resp.ok:
        raise SystemExit(f"❌ Failed to insert blocks after {after_block_id}: {resp.status_code} {resp.text}")


def delete_block(block_id: str) -> None:
    """Archive (delete) a block."""
    url = f"{BASE}/blocks/{block_id}"
    payload = {"archived": True}
    resp = requests.patch(url, headers=HEADERS, json=payload)
    if not resp.ok:
        raise SystemExit(f"❌ Failed to delete block {block_id}: {resp.status_code} {resp.text}")

def clone_todo_block(block: Dict) -> Dict:
    """Prepare a copy of a to_do block with unchecked state."""
    if block.get("type") != "to_do":
        raise ValueError("Not a to_do block")
    src = block["to_do"]
    new_block = {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": src.get("rich_text", []),
            "checked": False,
            "color": src.get("color", "default"),
        }
    }
    return new_block

def partition_by_sections(blocks: List[Dict]) -> Dict[str, List[Dict]]:
    """Return lists of blocks for each section and store header indices on the list object via attributes."""
    idx_today = idx_tomorrow = idx_backlog = idx_daily = None
    for i, b in enumerate(blocks):
        if idx_daily is None and is_header_with_text(b, ["Daily"]):
            idx_daily = i
        if idx_today is None and is_header_with_text(b, ["Today"]):
            idx_today = i
        if idx_tomorrow is None and is_header_with_text(b, ["Tomorrow"]):
            idx_tomorrow = i
        if idx_backlog is None and is_header_with_text(b, ["Backlog"]):
            idx_backlog = i
    n = len(blocks)
    sections = {"daily": [], "today": [], "tomorrow": [], "backlog": []}
    # compute slices
    if idx_daily is not None:
        start = idx_daily + 1
        end = min([x for x in [idx_today, idx_tomorrow, idx_backlog] if x is not None], default=n)
        sections["daily"] = blocks[start:end]
    if idx_today is not None:
        start = idx_today + 1
        end = min([x for x in [idx_tomorrow, idx_backlog] if x is not None], default=n)
        sections["today"] = blocks[start:end]
    if idx_tomorrow is not None:
        start = idx_tomorrow + 1
        end = min([x for x in [idx_backlog] if x is not None], default=n)
        sections["tomorrow"] = blocks[start:end]
    if idx_backlog is not None:
        start = idx_backlog + 1
        end = n
        sections["backlog"] = blocks[start:end]
    # attach header indices for later insertions
    # Removed line that sets dynamic attribute on list:
    # for k in sections:
    #     sections[k].header_index = {"today": idx_today, "tomorrow": idx_tomorrow, "backlog": idx_backlog}[k]
    return sections

def get_section_range(blocks: List[Dict], section_name: str) -> Tuple[int, int]:
    """Return (start, end) indices (slice) for a section's content within blocks list."""
    today_idx = tomorrow_idx = backlog_idx = daily_idx = None
    for i, b in enumerate(blocks):
        if daily_idx is None and is_header_with_text(b, ["Daily"]):
            daily_idx = i
        if today_idx is None and is_header_with_text(b, ["Today"]):
            today_idx = i
        if tomorrow_idx is None and is_header_with_text(b, ["Tomorrow"]):
            tomorrow_idx = i
        if backlog_idx is None and is_header_with_text(b, ["Backlog"]):
            backlog_idx = i

    n = len(blocks)
    if section_name == "daily" and daily_idx is not None:
        start = daily_idx + 1
        end_candidates = [idx for idx in [today_idx, tomorrow_idx, backlog_idx] if idx is not None]
        end = min(end_candidates) if end_candidates else n
        return start, end
    if section_name == "today" and today_idx is not None:
        start = today_idx + 1
        end_candidates = [idx for idx in [tomorrow_idx, backlog_idx] if idx is not None]
        end = min(end_candidates) if end_candidates else n
        return start, end
    if section_name == "tomorrow" and tomorrow_idx is not None:
        start = tomorrow_idx + 1
        end = backlog_idx if backlog_idx is not None else n
        return start, end
    if section_name == "backlog" and backlog_idx is not None:
        start = backlog_idx + 1
        end = n
        return start, end
    return (0, 0)

def remove_empty_paragraphs_in_slice(blocks: List[Dict], start: int, end: int) -> None:
    """Delete empty paragraph blocks inside [start, end) slice to keep checkbox list contiguous."""
    # Collect ids to delete first to avoid modifying paging while iterating
    ids_to_delete: List[str] = []
    for i in range(start, end):
        b = blocks[i]
        if is_empty_paragraph(b):
            ids_to_delete.append(b["id"])
    for bid in ids_to_delete:
        delete_block(bid)


def section_header_id(blocks: List[Dict], section: str) -> Optional[str]:
    for i, b in enumerate(blocks):
        if is_header_with_text(b, [section.capitalize()]):
            return b["id"]
    return None

def cleanup_todo_page(page_id: str) -> None:
    """Clean up the To-Do page:
       - Remove completed tasks from Backlog
       - Move incomplete Today tasks to Backlog
       - Remove completed Today tasks
    """
    blocks = get_all_children(page_id)

    parts = partition_by_sections(blocks)

    # DAILY: compute stats and reset checkboxes
    daily_blocks = parts.get("daily", [])
    daily_total = 0
    daily_completed = 0
    for b in daily_blocks:
        if b.get("type") != "to_do":
            continue
        daily_total += 1
        if b["to_do"].get("checked"):
            daily_completed += 1
        # uncheck all daily todos
        set_todo_checked(b["id"], False)
    # Log to Daily Completion (if there were any todos or the DB exists)
    if daily_total > 0:
        try:
            log_daily_completion(daily_completed, daily_total)
        except Exception as e:
            # non-fatal
            print(f"⚠️  Failed to write Daily Completion: {e}")

    today_header = section_header_id(blocks, "today")
    tomorrow_header = section_header_id(blocks, "tomorrow")
    backlog_header = section_header_id(blocks, "backlog")
    if not today_header:
        raise SystemExit("❌ Could not find 'Today:' header. Make sure it's a Heading or a Paragraph with text 'Today:'.")
    if not backlog_header:
        raise SystemExit("❌ Could not find 'Backlog:' header. Make sure it's a Heading or a Paragraph with text 'Backlog:'.")
    # 'Tomorrow' is optional; only required if present visually

    start_today, end_today = get_section_range(blocks, "today")
    start_backlog, end_backlog = get_section_range(blocks, "backlog")
    # Always insert right after the section header to avoid drifting past other blocks
    today_anchor = today_header
    backlog_anchor = backlog_header

    # Handle Tomorrow: move incomplete to Today, remove completed
    tomorrow_blocks = parts.get("tomorrow", [])
    to_append_today: List[Dict] = []
    to_delete_tomorrow_ids: List[str] = []

    for b in tomorrow_blocks:
        if b.get("type") != "to_do":
            continue
        if b["to_do"].get("checked", False):
            try:
                log_done_item(rich_text_to_plain(b))
            except Exception as e:
                print(f"⚠️  Failed to log Done item: {e}")
            to_delete_tomorrow_ids.append(b["id"])  # completed -> delete
        else:
            to_append_today.append(clone_todo_block(b))  # unchecked -> move to Today
            to_delete_tomorrow_ids.append(b["id"])

    # Append moved items (inside Today section)
    if to_append_today:
        append_blocks_after(page_id, today_anchor, to_append_today)

    # Delete from Tomorrow
    for bid in to_delete_tomorrow_ids:
        delete_block(bid)

    today_blocks = parts["today"]
    backlog_blocks = parts["backlog"]

    # Remove completed tasks from Backlog
    for b in backlog_blocks:
        if b.get("type") == "to_do" and b["to_do"].get("checked"):
            try:
                log_done_item(rich_text_to_plain(b))
            except Exception as e:
                print(f"⚠️  Failed to log Done item: {e}")
            delete_block(b["id"])

    # Move incomplete Today tasks to Backlog, delete all from Today
    to_append: List[Dict] = []
    to_delete_ids: List[str] = []

    for b in today_blocks:
        if b.get("type") != "to_do":
            continue
        checked = b["to_do"].get("checked", False)
        if checked:
            try:
                log_done_item(rich_text_to_plain(b))
            except Exception as e:
                print(f"⚠️  Failed to log Done item: {e}")
            to_delete_ids.append(b["id"])
        else:
            to_append.append(clone_todo_block(b))
            to_delete_ids.append(b["id"])

    if to_append:
        # Re-read blocks in case structure changed, but we still prefer inserting after backlog header
        blocks = get_all_children(page_id)
        backlog_header = section_header_id(blocks, "backlog") or backlog_header
        append_blocks_after(page_id, backlog_header, to_append)

    for bid in to_delete_ids:
        delete_block(bid)

    # Merge Backlog checkboxes into a single contiguous list (remove empty paragraphs)
    blocks_after_backlog_append = get_all_children(page_id)
    start_b, end_b = get_section_range(blocks_after_backlog_append, "backlog")
    if end_b > start_b:
        remove_empty_paragraphs_in_slice(blocks_after_backlog_append, start_b, end_b)

    # Ensure Today section has at least one empty checkbox
    try:
        blocks_after = get_all_children(page_id)
        parts_after = partition_by_sections(blocks_after)
        has_today_todo = any(b.get("type") == "to_do" for b in parts_after.get("today", []))
        if not has_today_todo:
            header_id = section_header_id(blocks_after, "today")
            if header_id:
                append_blocks_after(page_id, header_id, [{
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": ""}}],
                        "checked": False,
                        "color": "default",
                    }
                }])

        has_tomorrow_todo = any(b.get("type") == "to_do" for b in parts_after.get("tomorrow", []))
        if not has_tomorrow_todo:
            header_id = section_header_id(blocks_after, "tomorrow")
            if header_id:
                append_blocks_after(page_id, header_id, [{
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": ""}}],
                        "checked": False,
                        "color": "default",
                    }
                }])
        has_daily_todo = any(b.get("type") == "to_do" for b in parts_after.get("daily", []))
        if not has_daily_todo:
            header_id = section_header_id(blocks_after, "daily")
            if header_id:
                append_blocks_after(page_id, header_id, [{
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": ""}}],
                        "checked": False,
                        "color": "default",
                    }
                }])
    except Exception as e:
        raise SystemExit(f"❌ Failed while ensuring placeholder to_do in Today: {e}")

def main():
    if not NOTION_TOKEN:
        raise SystemExit("❌ Set NOTION_TOKEN env var (Internal Integration Token).")
    if not PAGE_ID:
        raise SystemExit("❌ Set NOTION_PAGE_ID env var (Notion page ID/URL component).")

    # Verify access to the page (404 also indicates the integration isn't invited to the page)
    get_page(PAGE_ID)

    try:
        ensure_done_db_id()
        ensure_daily_comp_db_id()
    except Exception as e:
        print(f"⚠️  DB discovery warning: {e}")

    cleanup_todo_page(PAGE_ID)
    print("✅ Done: Today cleaned, unchecked moved to Backlog, completed removed.")

if __name__ == "__main__":
    main()