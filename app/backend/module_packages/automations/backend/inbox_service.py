"""Automation Inbox — workflow-written reviewable items inside the Automations module.

n8n workflows POST structured items (via the automation token); humans review them
with per-item actions (interested / passed / offer_made / closed). Items live in
Brain JSON per scope: business in the _team pool (survives account deletion),
personal in the user's own Brain. Named inboxes route items by workflow_key and
carry their own notify + reviewer lists (owner decision 2026-07-12).
"""

import logging
import uuid
from datetime import datetime, timezone

from services.auth_service import get_user_by_name
from services.file_service import automation_inbox_path, read_json, write_json

logger = logging.getLogger("logcore.automation_inbox")

DEFAULT_INBOX_NAME = "General"
ITEM_STATUSES = {"new", "interested", "passed", "offer_made", "closed"}
MAX_ITEMS_PER_SCOPE = 500
MAX_BATCH = 100
_TITLE_MAX = 200
_SUMMARY_MAX = 2000
_URL_MAX = 1000
_EXTERNAL_ID_MAX = 500
_NOTE_MAX = 1000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_store(store_user: str) -> dict:
    data = read_json(automation_inbox_path(store_user), default={"inboxes": [], "items": []})
    data.setdefault("inboxes", [])
    data.setdefault("items", [])
    return data


def _save(store_user: str, data: dict) -> None:
    write_json(automation_inbox_path(store_user), data)


# ---------------------------------------------------------------------------
# Inboxes
# ---------------------------------------------------------------------------


def _validate_names(names: list[str] | None, field: str) -> list[str]:
    cleaned = list(dict.fromkeys(n.strip() for n in (names or []) if n and n.strip()))
    for name in cleaned:
        if get_user_by_name(name) is None:
            raise ValueError(f"Unknown user {name!r} in {field}")
    return cleaned


def _clean_workflows(keys: list[str] | None) -> list[str]:
    return list(dict.fromkeys(str(k).strip()[:100] for k in (keys or []) if str(k).strip()))[:50]


def create_inbox(
    store_user: str,
    name: str,
    notify: list[str] | None = None,
    reviewers: list[str] | None = None,
    workflows: list[str] | None = None,
) -> dict:
    name = (name or "").strip()[:80]
    if not name:
        raise ValueError("Inbox name is required")
    data = load_store(store_user)
    if any(b["name"].lower() == name.lower() for b in data["inboxes"]):
        raise ValueError(f"Inbox {name!r} already exists")
    inbox = {
        "id": str(uuid.uuid4()),
        "name": name,
        "notify": _validate_names(notify, "notify"),
        "reviewers": _validate_names(reviewers, "reviewers"),
        "workflows": _clean_workflows(workflows),
        "created_at": _now_iso(),
    }
    data["inboxes"].append(inbox)
    _save(store_user, data)
    return inbox


def update_inbox(store_user: str, inbox_id: str, updates: dict) -> dict | None:
    data = load_store(store_user)
    inbox = next((b for b in data["inboxes"] if b["id"] == inbox_id), None)
    if inbox is None:
        return None
    if "name" in updates and updates["name"]:
        new_name = str(updates["name"]).strip()[:80]
        if any(
            b["name"].lower() == new_name.lower() and b["id"] != inbox_id for b in data["inboxes"]
        ):
            raise ValueError(f"Inbox {new_name!r} already exists")
        inbox["name"] = new_name
    if "notify" in updates and updates["notify"] is not None:
        inbox["notify"] = _validate_names(updates["notify"], "notify")
    if "reviewers" in updates and updates["reviewers"] is not None:
        inbox["reviewers"] = _validate_names(updates["reviewers"], "reviewers")
    if "workflows" in updates and updates["workflows"] is not None:
        inbox["workflows"] = _clean_workflows(updates["workflows"])
    _save(store_user, data)
    return inbox


def delete_inbox(store_user: str, inbox_id: str) -> bool:
    data = load_store(store_user)
    if not any(b["id"] == inbox_id for b in data["inboxes"]):
        return False
    count = sum(1 for i in data["items"] if i.get("inbox_id") == inbox_id)
    if count:
        raise ValueError(f"This inbox still has {count} item(s) — clear them first")
    data["inboxes"] = [b for b in data["inboxes"] if b["id"] != inbox_id]
    _save(store_user, data)
    return True


def _route_inbox(data: dict, workflow_key: str) -> dict:
    """Inbox claiming this workflow_key, else the General inbox (created once)."""
    for inbox in data["inboxes"]:
        if workflow_key in (inbox.get("workflows") or []):
            return inbox
    general = next(
        (b for b in data["inboxes"] if b["name"].lower() == DEFAULT_INBOX_NAME.lower()), None
    )
    if general is None:
        general = {
            "id": str(uuid.uuid4()),
            "name": DEFAULT_INBOX_NAME,
            "notify": [],
            "reviewers": [],
            "workflows": [],
            "created_at": _now_iso(),
        }
        data["inboxes"].append(general)
    return general


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


def _clean_item(raw: dict, workflow_key: str, inbox_id: str) -> dict:
    external_id = str(raw.get("external_id") or "").strip()[:_EXTERNAL_ID_MAX]
    title = str(raw.get("title") or "").strip()[:_TITLE_MAX]
    if not external_id or not title:
        raise ValueError("Each item needs an external_id and a title")
    fields = raw.get("fields") or {}
    if not isinstance(fields, dict) or len(fields) > 50:
        raise ValueError("fields must be an object with at most 50 keys")
    return {
        "id": str(uuid.uuid4()),
        "inbox_id": inbox_id,
        "workflow_key": workflow_key,
        "external_id": external_id,
        "title": title,
        "summary": (str(raw.get("summary")).strip()[:_SUMMARY_MAX] if raw.get("summary") else None),
        "url": (str(raw.get("url")).strip()[:_URL_MAX] if raw.get("url") else None),
        "fields": fields,
        "status": "new",
        "status_by": None,
        "status_at": None,
        "note": None,
        "received_at": _now_iso(),
    }


def _trim(data: dict) -> None:
    """Cap the scope at MAX_ITEMS_PER_SCOPE — drop oldest reviewed items first,
    then oldest new ones if a runaway workflow floods the store."""
    items = data["items"]
    if len(items) <= MAX_ITEMS_PER_SCOPE:
        return
    overflow = len(items) - MAX_ITEMS_PER_SCOPE
    reviewed = sorted(
        (i for i in items if i.get("status") != "new"), key=lambda i: i.get("received_at") or ""
    )
    drop = {i["id"] for i in reviewed[:overflow]}
    if len(drop) < overflow:
        fresh = sorted(
            (i for i in items if i.get("status") == "new"), key=lambda i: i.get("received_at") or ""
        )
        drop.update(i["id"] for i in fresh[: overflow - len(drop)])
    data["items"] = [i for i in items if i["id"] not in drop]


def add_items(
    store_user: str, workflow_key: str, items: list[dict], workspace: str = "personal"
) -> dict:
    """Dedup by (workflow_key, external_id), route to the claiming inbox, trim,
    and notify the inbox's recipients (batched — one notification per person)."""
    workflow_key = (workflow_key or "").strip()[:100]
    if not workflow_key:
        raise ValueError("workflow_key is required")
    if len(items) > MAX_BATCH:
        raise ValueError(f"At most {MAX_BATCH} items per batch")
    data = load_store(store_user)
    inbox = _route_inbox(data, workflow_key)
    seen = {(i.get("workflow_key"), i.get("external_id")) for i in data["items"]}
    created: list[dict] = []
    skipped = 0
    for raw in items:
        item = _clean_item(raw, workflow_key, inbox["id"])
        if (workflow_key, item["external_id"]) in seen:
            skipped += 1
            continue
        seen.add((workflow_key, item["external_id"]))
        data["items"].append(item)
        created.append(item)
    if created:
        _trim(data)
    _save(store_user, data)  # General inbox may have been created even if all skipped
    if created:
        _notify_new_items(store_user, inbox, created, workspace)
    return {"created": len(created), "skipped": skipped, "inbox_id": inbox["id"]}


def _notify_new_items(store_user: str, inbox: dict, created: list[dict], workspace: str) -> None:
    from services import suggestions_service

    recipients = set(inbox.get("notify") or [])
    if store_user not in ("_team", "_household"):
        recipients.add(store_user)  # personal scope: owner is implicitly notified
    titles = ", ".join(i["title"] for i in created[:3])
    if len(created) > 3:
        titles += ", …"
    for name in sorted(recipients):
        try:
            suggestions_service.notify_user(
                name,
                title=f"{inbox['name']}: {len(created)} new item{'s' if len(created) != 1 else ''}",
                body=titles,
                source="automations",
                action={"type": "open_inbox", "workspace": workspace, "inbox_id": inbox["id"]},
                url=f"/automations?view=inbox&inbox={inbox['id']}",
            )
        except Exception:
            logger.warning("Inbox notification to %s failed", name, exc_info=True)


def seen_ids(store_user: str, workflow_key: str | None = None) -> list[str]:
    data = load_store(store_user)
    return [
        i["external_id"]
        for i in data["items"]
        if workflow_key is None or i.get("workflow_key") == workflow_key
    ]


def set_item_status(
    store_user: str, item_id: str, status: str, by: str, note: str | None = None
) -> dict | None:
    if status not in ITEM_STATUSES:
        raise ValueError(f"Invalid status {status!r}. Valid: {sorted(ITEM_STATUSES)}")
    data = load_store(store_user)
    item = next((i for i in data["items"] if i["id"] == item_id), None)
    if item is None:
        return None
    item["status"] = status
    item["status_by"] = by
    item["status_at"] = _now_iso()
    if note is not None:
        item["note"] = str(note).strip()[:_NOTE_MAX] or None
    _save(store_user, data)
    return item


def delete_item(store_user: str, item_id: str) -> bool:
    data = load_store(store_user)
    before = len(data["items"])
    data["items"] = [i for i in data["items"] if i["id"] != item_id]
    if len(data["items"]) == before:
        return False
    _save(store_user, data)
    return True


def find_item(store_user: str, item_id: str) -> tuple[dict, dict] | None:
    """Return (item, its inbox) or None."""
    data = load_store(store_user)
    item = next((i for i in data["items"] if i["id"] == item_id), None)
    if item is None:
        return None
    inbox = next((b for b in data["inboxes"] if b["id"] == item.get("inbox_id")), None)
    return item, (inbox or {})
