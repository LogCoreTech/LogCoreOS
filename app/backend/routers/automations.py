"""Automations module — import and run n8n workflows."""
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from routers.auth import get_current_user, require_admin, require_module
from services import n8n_service
from services.rate_limiter import rate_limit

logger = logging.getLogger("logcore.automations")

_require_automations = require_module("automations")
_read_limit  = rate_limit(30, 60)
_write_limit = rate_limit(10, 60)

router = APIRouter()


class N8nConfigRequest(BaseModel):
    url: str
    api_key: str


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
    n8n_service.save_config({"url": req.url.strip(), "api_key": req.api_key.strip()})
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
    from services.file_service import read_json, brain_path
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

    return record


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


@router.post("/{record_id}/run")
def run_automation(
    record_id: str,
    current_user: dict = Depends(_require_automations),
    _rl: None = Depends(_write_limit),
):
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
    n8n_service.update_last_run(record_id, current_user["name"], record["scope"],
                                datetime.now(timezone.utc).isoformat())
    return result


@router.post("/{record_id}/activate")
def activate_automation(
    record_id: str,
    current_user: dict = Depends(_require_automations),
    _rl: None = Depends(_write_limit),
):
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
