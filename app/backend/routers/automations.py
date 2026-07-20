"""Automations module — import and run n8n workflows + the Automation Inbox."""

import json
import logging
import re

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, field_validator

from routers.auth import get_current_user, get_workspace, require_admin, require_module
from services import automation_inbox_service as inbox_service
from services import automations_config, n8n_service
from services.auth_service import get_user_by_name
from services.rate_limiter import rate_limit

logger = logging.getLogger("logcore.automations")

_require_automations = require_module("automations")
_read_limit = rate_limit(30, 60)
_write_limit = rate_limit(10, 60)
_automation_limit = rate_limit(30, 60)

router = APIRouter()


class N8nConfigRequest(BaseModel):
    url: str
    api_key: str
    force_on: bool | None = None


class InboxItemIn(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=500)
    title: str = Field(..., min_length=1, max_length=200)
    summary: str | None = Field(None, max_length=2000)
    url: str | None = Field(None, max_length=1000)
    fields: dict = Field(default={})

    @field_validator("url")
    @classmethod
    def _url_must_be_http(cls, v: str | None) -> str | None:
        """Reject any non-http(s) URL. The inbox item's url is rendered as a
        clickable link in the reviewer's (often admin) authenticated origin, so a
        `javascript:`/`data:` scheme would be a stored-XSS sink. Land listings and
        every legitimate source always use http(s)."""
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if not re.match(r"^https?://", v, re.IGNORECASE):
            raise ValueError("url must be an http:// or https:// URL")
        return v


class AutomationInboxPost(BaseModel):
    user: str = Field(..., max_length=100)
    workspace: str = Field("business", pattern="^(personal|business)$")
    workflow_key: str = Field(..., min_length=1, max_length=100)
    items: list[InboxItemIn] = Field(..., max_length=100)


class InboxCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    notify: list[str] = Field(default=[], max_length=50)
    reviewers: list[str] = Field(default=[], max_length=50)
    workflows: list[str] = Field(default=[], max_length=50)


class InboxUpdate(BaseModel):
    name: str | None = Field(None, max_length=80)
    notify: list[str] | None = Field(None, max_length=50)
    reviewers: list[str] | None = Field(None, max_length=50)
    workflows: list[str] | None = Field(None, max_length=50)


class ItemStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(new|interested|passed|offer_made|closed)$")
    note: str | None = Field(None, max_length=1000)


# ── n8n admin endpoints (must come before /{id}/... routes) ───────────────────


@router.get("/n8n/status")
def n8n_status(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_read_limit),
):
    return n8n_service.test_connection()


@router.post("/n8n/config")
def save_n8n_config(
    req: N8nConfigRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    n8n_service.save_config(
        {"url": req.url.strip(), "api_key": req.api_key.strip(), "force_on": req.force_on}
    )
    # Attaching an external instance stops the bundled container; the force-on
    # override / stored-workflow count decide otherwise.
    n8n_service.reconcile()
    return {"ok": True}


@router.post("/n8n/sync-workflows")
def trigger_workflow_sync(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    """Manually trigger business workflow sync against the remote stub source."""
    result = n8n_service.sync_business_workflows()
    return result


@router.post("/n8n/sync-secrets")
def sync_secrets_to_n8n(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    """Write cached Infisical secrets to docker/n8n.env and restart n8n."""
    from services.file_service import brain_path, read_json

    cache_path = brain_path() / "_system" / "infisical_cache.json"
    cache = read_json(cache_path, default={})
    secrets = cache.get("secrets", {})
    if not secrets:
        raise HTTPException(
            status_code=400,
            detail="No Infisical cache found. Connect Infisical first via the Managed Hosting card.",
        )
    n8n_service.write_n8n_env(secrets)
    try:
        n8n_service.restart_n8n()
        return {"ok": True, "message": f"Synced {len(secrets)} secret(s) and restarted n8n."}
    except Exception as exc:
        return {"ok": True, "message": f"Secrets written to n8n.env but restart failed: {exc}"}


# ── Workflow list ──────────────────────────────────────────────────────────────


@router.get("")
def list_automations(
    scope: str = "all",
    current_user: dict = Depends(_require_automations),
    _rl: None = Depends(_read_limit),
):
    if scope not in ("personal", "business", "all"):
        raise HTTPException(status_code=400, detail="scope must be personal, business, or all")
    # Non-admins only see personal + business (no filter needed); restrict if needed
    return n8n_service.get_all_workflows(scope, current_user["name"])


# ── Import workflow ────────────────────────────────────────────────────────────


@router.post("/import")
async def import_workflow(
    file: UploadFile = File(...),
    name: str = Form(""),
    scope: str = Form("personal"),
    tags: str = Form("[]"),
    current_user: dict = Depends(_require_automations),
    _rl: None = Depends(_write_limit),
):
    if scope == "business" and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can import business workflows.")
    if scope not in ("personal", "business"):
        raise HTTPException(status_code=400, detail="scope must be personal or business")

    try:
        raw = await file.read()
        wf_json = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    try:
        tag_list = json.loads(tags) if tags else []
    except json.JSONDecodeError:
        tag_list = []

    try:
        record = n8n_service.import_workflow(
            wf_json=wf_json,
            scope=scope,
            owner=current_user["name"],
            name=name.strip() or None,
            tags=tag_list,
        )
    except Exception as exc:
        logger.warning("n8n import failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"n8n import failed: {exc}")

    n8n_service.reconcile()  # first stored workflow → ensure the bundled n8n is up
    return record


# ── Automation Inbox ───────────────────────────────────────────────────────────
# Workflow-written reviewable items. n8n posts via the automation token; humans
# review from the Automations page. Business scope lives in the _team pool.


def _require_automation_token(x_automation_token: str = Header("")) -> None:
    if not automations_config.verify_api_token(x_automation_token):
        raise HTTPException(status_code=401, detail="Invalid automation token")


def _inbox_store(current_user: dict, workspace: str) -> str:
    """JWT calls: business workspace reviews the shared _team inbox; personal
    reviews the caller's own."""
    return "_team" if workspace == "business" else current_user["name"]


def _can_manage_inboxes(current_user: dict, workspace: str) -> bool:
    """Business inboxes are admin-managed; a personal inbox belongs to its owner."""
    return workspace != "business" or current_user.get("role") == "admin"


def _can_act_on(inbox: dict, current_user: dict, workspace: str) -> bool:
    """Status changes: admin, personal-scope owner, or a picked reviewer."""
    if current_user.get("role") == "admin" or workspace != "business":
        return True
    return current_user["name"] in (inbox.get("reviewers") or [])


@router.post("/inbox/items", status_code=201)
def automation_post_items(
    req: AutomationInboxPost,
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    """n8n → LogCore: post a batch of reviewable items. Dedup by
    (workflow_key, external_id); routed to the inbox claiming the key
    (else General); the inbox's notify list gets one batched notification."""
    if req.user != "_team" and get_user_by_name(req.user) is None:
        raise HTTPException(status_code=404, detail=f"Unknown user {req.user!r}")
    try:
        return inbox_service.add_items(
            req.user,
            req.workflow_key,
            [i.model_dump() for i in req.items],
            workspace=req.workspace,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/inbox/seen")
def automation_seen_ids(
    user: str,
    workflow_key: str | None = None,
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    """external_ids already in the store — lets a workflow skip re-qualifying
    listings it has already submitted (reviewed or not)."""
    if user != "_team" and get_user_by_name(user) is None:
        raise HTTPException(status_code=404, detail=f"Unknown user {user!r}")
    return {"seen": inbox_service.seen_ids(user, workflow_key)}


@router.get("/inbox")
def get_inbox(
    current_user: dict = Depends(_require_automations),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store = _inbox_store(current_user, workspace)
    data = inbox_service.load_store(store)
    can_manage = _can_manage_inboxes(current_user, workspace)
    inboxes = [
        {
            **b,
            "_can_act": _can_act_on(b, current_user, workspace),
            "_can_manage": can_manage,
        }
        for b in data["inboxes"]
    ]
    return {"inboxes": inboxes, "items": data["items"]}


@router.post("/inboxes", status_code=201)
def create_inbox(
    req: InboxCreate,
    current_user: dict = Depends(_require_automations),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    if not _can_manage_inboxes(current_user, workspace):
        raise HTTPException(status_code=403, detail="Only admins can manage business inboxes")
    try:
        return inbox_service.create_inbox(
            _inbox_store(current_user, workspace),
            req.name,
            notify=req.notify,
            reviewers=req.reviewers,
            workflows=req.workflows,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/inboxes/{inbox_id}")
def update_inbox(
    inbox_id: str,
    req: InboxUpdate,
    current_user: dict = Depends(_require_automations),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    if not _can_manage_inboxes(current_user, workspace):
        raise HTTPException(status_code=403, detail="Only admins can manage business inboxes")
    try:
        result = inbox_service.update_inbox(
            _inbox_store(current_user, workspace), inbox_id, req.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Inbox not found")
    return result


@router.delete("/inboxes/{inbox_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inbox(
    inbox_id: str,
    current_user: dict = Depends(_require_automations),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    if not _can_manage_inboxes(current_user, workspace):
        raise HTTPException(status_code=403, detail="Only admins can manage business inboxes")
    try:
        found = inbox_service.delete_inbox(_inbox_store(current_user, workspace), inbox_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not found:
        raise HTTPException(status_code=404, detail="Inbox not found")


@router.post("/inbox/items/{item_id}/status")
def set_item_status(
    item_id: str,
    req: ItemStatusUpdate,
    current_user: dict = Depends(_require_automations),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store = _inbox_store(current_user, workspace)
    found = inbox_service.find_item(store, item_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Item not found")
    _item, inbox = found
    if not _can_act_on(inbox, current_user, workspace):
        raise HTTPException(
            status_code=403, detail="Only a reviewer of this inbox can change item status"
        )
    try:
        return inbox_service.set_item_status(
            store, item_id, req.status, by=current_user["name"], note=req.note
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/inbox/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inbox_item(
    item_id: str,
    current_user: dict = Depends(_require_automations),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    if not _can_manage_inboxes(current_user, workspace):
        raise HTTPException(status_code=403, detail="Only admins can delete business inbox items")
    if not inbox_service.delete_item(_inbox_store(current_user, workspace), item_id):
        raise HTTPException(status_code=404, detail="Item not found")


# ── Per-workflow endpoints ─────────────────────────────────────────────────────


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation(
    record_id: str,
    current_user: dict = Depends(_require_automations),
    _rl: None = Depends(_write_limit),
):
    record = n8n_service.find_workflow(record_id, current_user["name"])
    if not record:
        raise HTTPException(status_code=404, detail="Workflow not found")

    is_admin = current_user.get("role") == "admin"
    is_owner = record.get("scope") == "personal"  # personal records belong to the requesting user

    if not (is_owner or is_admin):
        raise HTTPException(status_code=403, detail="Not authorised to delete this workflow")

    try:
        n8n_service.delete_workflow(record_id, record["scope"], current_user["name"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.warning("Delete workflow failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Delete failed: {exc}")

    n8n_service.reconcile()  # last workflow removed + no external → stop the bundled n8n


@router.post("/{record_id}/run")
def run_automation(
    record_id: str,
    current_user: dict = Depends(_require_automations),
    _rl: None = Depends(_write_limit),
):
    if not n8n_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="n8n is not configured. Go to Admin → Automations to set up n8n.",
        )
    record = n8n_service.find_workflow(record_id, current_user["name"])
    if not record:
        raise HTTPException(status_code=404, detail="Workflow not found")

    n8n_id = record.get("n8n_id")
    if not n8n_id:
        raise HTTPException(status_code=400, detail="Workflow has no n8n ID")

    try:
        result = n8n_service.execute_workflow(n8n_id)
    except Exception as exc:
        logger.warning("n8n execute failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Execution failed: {exc}")

    from datetime import datetime, timezone

    n8n_service.update_last_run(
        record_id, current_user["name"], record["scope"], datetime.now(timezone.utc).isoformat()
    )
    return result


@router.post("/{record_id}/activate")
def activate_automation(
    record_id: str,
    current_user: dict = Depends(_require_automations),
    _rl: None = Depends(_write_limit),
):
    if not n8n_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="n8n is not configured. Go to Admin → Automations to set up n8n.",
        )
    record = n8n_service.find_workflow(record_id, current_user["name"])
    if not record:
        raise HTTPException(status_code=404, detail="Workflow not found")
    is_admin = current_user.get("role") == "admin"
    if record.get("scope") == "business" and not is_admin:
        raise HTTPException(status_code=403, detail="Only admins can activate business workflows")
    n8n_id = record.get("n8n_id")
    if not n8n_id:
        raise HTTPException(status_code=400, detail="Workflow has no n8n ID")
    try:
        n8n_service.activate_workflow(n8n_id)
        n8n_service.update_active_status(record_id, current_user["name"], record["scope"], True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Activation failed: {exc}")
    return {"ok": True, "active": True}


@router.post("/{record_id}/deactivate")
def deactivate_automation(
    record_id: str,
    current_user: dict = Depends(_require_automations),
    _rl: None = Depends(_write_limit),
):
    if not n8n_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="n8n is not configured. Go to Admin → Automations to set up n8n.",
        )
    record = n8n_service.find_workflow(record_id, current_user["name"])
    if not record:
        raise HTTPException(status_code=404, detail="Workflow not found")
    is_admin = current_user.get("role") == "admin"
    if record.get("scope") == "business" and not is_admin:
        raise HTTPException(status_code=403, detail="Only admins can deactivate business workflows")
    n8n_id = record.get("n8n_id")
    if not n8n_id:
        raise HTTPException(status_code=400, detail="Workflow has no n8n ID")
    try:
        n8n_service.deactivate_workflow(n8n_id)
        n8n_service.update_active_status(record_id, current_user["name"], record["scope"], False)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Deactivation failed: {exc}")
    return {"ok": True, "active": False}


@router.get("/{record_id}/logs")
def get_logs(
    record_id: str,
    limit: int = 10,
    current_user: dict = Depends(_require_automations),
    _rl: None = Depends(_read_limit),
):
    if not n8n_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="n8n is not configured. Go to Admin → Automations to set up n8n.",
        )
    record = n8n_service.find_workflow(record_id, current_user["name"])
    if not record:
        raise HTTPException(status_code=404, detail="Workflow not found")

    n8n_id = record.get("n8n_id")
    if not n8n_id:
        return []

    try:
        return n8n_service.get_executions(n8n_id, limit=min(limit, 50))
    except Exception as exc:
        logger.warning("n8n get executions failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Failed to fetch logs: {exc}")
