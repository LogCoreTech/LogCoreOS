"""n8n service — API client and Brain metadata management for the Automations module."""
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from config import settings
from services.file_service import (
    automations_path,
    brain_path,
    read_json,
    system_automations_path,
    write_json,
)

logger = logging.getLogger("logcore.n8n")

_CONFIG_PATH = lambda: brain_path() / "_system" / "n8n_config.json"


def get_config() -> dict:
    """Read n8n config from Brain; fall back to settings defaults."""
    cfg = read_json(_CONFIG_PATH(), default={})
    return {
        "url": cfg.get("url") or settings.n8n_url,
        "api_key": cfg.get("api_key") or settings.n8n_api_key,
    }


def save_config(cfg: dict) -> None:
    write_json(_CONFIG_PATH(), cfg)


def _client() -> httpx.Client:
    cfg = get_config()
    return httpx.Client(
        base_url=cfg["url"].rstrip("/"),
        headers={"X-N8N-API-KEY": cfg["api_key"]},
        timeout=15.0,
    )


def test_connection() -> dict:
    """Test n8n connectivity. Returns {ok, url, error?}."""
    cfg = get_config()
    try:
        with _client() as c:
            r = c.get("/api/v1/workflows")
            ok = r.status_code < 400
            return {"ok": ok, "url": cfg["url"]}
    except Exception as exc:
        return {"ok": False, "url": cfg["url"], "error": str(exc)}


def import_workflow(
    wf_json: dict,
    scope: str,
    owner: str,
    name: str | None = None,
    tags: list | None = None,
) -> dict:
    """Import a workflow JSON into n8n and store Brain metadata."""
    wf_json = dict(wf_json)
    if name:
        wf_json["name"] = name

    with _client() as c:
        r = c.post("/api/v1/workflows", json=wf_json)
        r.raise_for_status()
        n8n_data = r.json()

    n8n_id = str(n8n_data.get("id", ""))
    record: dict = {
        "id": str(uuid4()),
        "n8n_id": n8n_id,
        "name": name or wf_json.get("name", "Untitled"),
        "scope": scope,
        "tags": tags or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run": None,
    }

    if scope == "business":
        _add_system_record(record)
    else:
        _add_user_record(owner, record)

    return record


def delete_workflow(record_id: str, scope: str, owner: str) -> None:
    """Delete a workflow from n8n and remove Brain metadata."""
    if scope == "business":
        path = system_automations_path()
        records = read_json(path, default=[])
        record = next((r for r in records if r["id"] == record_id), None)
        if not record:
            raise ValueError("Workflow not found")
        write_json(path, [r for r in records if r["id"] != record_id])
    else:
        path = automations_path(owner)
        records = read_json(path, default=[])
        record = next((r for r in records if r["id"] == record_id), None)
        if not record:
            raise ValueError("Workflow not found")
        write_json(path, [r for r in records if r["id"] != record_id])

    n8n_id = record.get("n8n_id")
    if n8n_id:
        try:
            with _client() as c:
                c.delete(f"/api/v1/workflows/{n8n_id}")
        except Exception as exc:
            logger.warning("Failed to delete n8n workflow %s: %s", n8n_id, exc)


def execute_workflow(n8n_id: str) -> dict:
    with _client() as c:
        r = c.post(f"/api/v1/workflows/{n8n_id}/execute")
        r.raise_for_status()
        return r.json()


def get_executions(n8n_id: str, limit: int = 10) -> list:
    with _client() as c:
        r = c.get("/api/v1/executions", params={"workflowId": n8n_id, "limit": limit})
        r.raise_for_status()
        return r.json().get("data", [])


def get_all_workflows(scope: str | None, user_name: str) -> list:
    """List workflows from Brain metadata."""
    result: list = []
    if scope in (None, "personal", "all"):
        result.extend(read_json(automations_path(user_name), default=[]))
    if scope in (None, "business", "all"):
        result.extend(read_json(system_automations_path(), default=[]))
    return result


def find_workflow(record_id: str, user_name: str) -> dict | None:
    for r in read_json(automations_path(user_name), default=[]):
        if r["id"] == record_id:
            return r
    for r in read_json(system_automations_path(), default=[]):
        if r["id"] == record_id:
            return r
    return None


def update_last_run(record_id: str, user_name: str, scope: str, timestamp: str) -> None:
    """Update last_run timestamp on a workflow record."""
    if scope == "business":
        path = system_automations_path()
    else:
        path = automations_path(user_name)
    records = read_json(path, default=[])
    for r in records:
        if r["id"] == record_id:
            r["last_run"] = timestamp
    write_json(path, records)


def write_n8n_env(secrets: dict) -> None:
    """Write Infisical secrets to docker/n8n.env for the n8n container."""
    repo_root = Path(__file__).parent.parent.parent.parent
    env_path = repo_root / "docker" / "n8n.env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in secrets.items()]
    env_path.write_text("\n".join(lines) + "\n")
    logger.info("Wrote %d secrets to %s", len(secrets), env_path)


def restart_n8n() -> None:
    """Restart logcore-n8n container via Docker CLI (socket is mounted read-only)."""
    subprocess.run(["docker", "restart", "logcore-n8n"], check=True, timeout=30)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _add_user_record(user_name: str, record: dict) -> None:
    path = automations_path(user_name)
    records = read_json(path, default=[])
    records.append(record)
    write_json(path, records)


def _add_system_record(record: dict) -> None:
    path = system_automations_path()
    records = read_json(path, default=[])
    records.append(record)
    write_json(path, records)
