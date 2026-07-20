"""n8n service — API client and Brain metadata management for the Automations module."""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import docker as docker_sdk
import httpx

from config import settings
from services.file_service import (
    automations_path,
    brain_path,
    read_json,
    system_automations_path,
    write_json,
)

STUBS_DIR = Path(__file__).parent.parent / "automations_stubs"

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
    """Merge into the stored config (preserves force_on unless supplied)."""
    existing = read_json(_CONFIG_PATH(), default={})
    existing.update({k: v for k, v in cfg.items() if v is not None})
    write_json(_CONFIG_PATH(), existing)


def is_configured() -> bool:
    return bool(get_config().get("api_key"))


# ── Bundled-container lifecycle ────────────────────────────────────────────────
# The bundled logcore-n8n container is only kept running when it is needed:
# when at least one workflow is stored, or the admin forces it on. Attaching an
# external n8n instance stops the bundled one. The app controls the container via
# the Docker socket (same mechanism as restart_n8n / the tunnel container).

_BUNDLED_HOSTS = ("n8n:5678", "logcore-n8n:5678", "localhost:5678", "127.0.0.1:5678")


def is_external() -> bool:
    """True when the configured URL points at an EXTERNAL n8n (not the bundled one)."""
    cfg = read_json(_CONFIG_PATH(), default={})
    url = (cfg.get("url") or "").strip()
    if not url:
        return False
    return not any(h in url for h in _BUNDLED_HOSTS)


def force_on() -> bool:
    return bool(read_json(_CONFIG_PATH(), default={}).get("force_on"))


def count_workflows() -> int:
    """Total stored workflows across all users (personal) + the business index."""
    total = len(read_json(system_automations_path(), default=[]) or [])
    users_dir = brain_path() / "USERS"
    if users_dir.exists():
        for d in users_dir.iterdir():
            if d.is_dir() and not d.name.startswith("_"):
                total += len(read_json(automations_path(d.name), default=[]) or [])
    return total


def _bundled_container():
    return docker_sdk.from_env().containers.get("logcore-n8n")


def start_n8n() -> None:
    try:
        c = _bundled_container()
        if c.status != "running":
            c.start()
    except Exception:
        logger.exception("could not start logcore-n8n container")


def stop_n8n() -> None:
    try:
        c = _bundled_container()
        if c.status == "running":
            c.stop()
    except Exception:
        logger.exception("could not stop logcore-n8n container")


def reconcile() -> str:
    """Start/stop the bundled n8n from the two signals + the admin override.
    Returns a short decision string. Never raises."""
    try:
        if is_external():
            stop_n8n()
            return "stopped:external"
        if force_on() or count_workflows() > 0:
            start_n8n()
            return "started"
        stop_n8n()
        return "stopped:idle"
    except Exception:
        logger.exception("n8n reconcile failed")
        return "error"


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
        "active": False,
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
        r = c.post(f"/api/v1/workflows/{n8n_id}/run")
        r.raise_for_status()
        return r.json()


def activate_workflow(n8n_id: str) -> None:
    with _client() as c:
        r = c.post(f"/api/v1/workflows/{n8n_id}/activate")
        r.raise_for_status()


def deactivate_workflow(n8n_id: str) -> None:
    with _client() as c:
        r = c.post(f"/api/v1/workflows/{n8n_id}/deactivate")
        r.raise_for_status()


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


def update_active_status(record_id: str, user_name: str, scope: str, active: bool) -> None:
    """Update active flag on a workflow record."""
    path = system_automations_path() if scope == "business" else automations_path(user_name)
    records = read_json(path, default=[])
    for r in records:
        if r["id"] == record_id:
            r["active"] = active
    write_json(path, records)


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


# Only these keys are ever written into docker/n8n.env. The n8n container's
# env is readable by every n8n workflow and n8n admin, so fanning the WHOLE
# secret vault (SECRET_KEY, ANTHROPIC_API_KEY, …) into it would leak app-wide
# secrets to workflow authors. Keys are allowed through only when they're clearly
# n8n-scoped: an N8N_ prefix, or an explicit operator allow-list.
_N8N_ENV_PREFIXES = ("N8N_",)


def _n8n_env_allowed(key: str) -> bool:
    if key.startswith(_N8N_ENV_PREFIXES):
        return True
    extra = {k.strip() for k in os.environ.get("N8N_ENV_ALLOWLIST", "").split(",") if k.strip()}
    return key in extra


def write_n8n_env(secrets: dict) -> None:
    """Write n8n-scoped Infisical secrets to docker/n8n.env for the n8n container.

    Only keys that pass ``_n8n_env_allowed()`` are written — the rest of the vault
    stays out of the workflow-readable env. Set N8N_ENV_ALLOWLIST (comma-separated)
    to pass through any additional non-N8N_-prefixed keys a workflow genuinely needs.
    """
    repo_root = Path(__file__).parent.parent.parent.parent
    env_path = repo_root / "docker" / "n8n.env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    allowed = {k: v for k, v in secrets.items() if _n8n_env_allowed(k)}
    skipped = len(secrets) - len(allowed)
    lines = [f"{k}={v}" for k, v in allowed.items()]
    env_path.write_text("\n".join(lines) + "\n")
    logger.info(
        "Wrote %d n8n-scoped secret(s) to %s (%d non-n8n key(s) withheld)",
        len(allowed),
        env_path,
        skipped,
    )


def restart_n8n() -> None:
    """Restart logcore-n8n container via Docker SDK."""
    client = docker_sdk.from_env()
    container = client.containers.get("logcore-n8n")
    container.restart()


# ── Business workflow auto-sync ────────────────────────────────────────────────


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _fetch_wf(base_url: str, token: str, key: str) -> tuple[dict, str]:
    """Fetch a workflow JSON from the remote source. Returns (parsed_json, raw_text)."""
    with httpx.Client(timeout=30.0) as c:
        r = c.get(
            f"{base_url.rstrip('/')}/{key}.json",
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json(), r.text


def sync_business_workflows() -> dict:
    """
    Reconcile auto-managed business workflows against stub files in automations_stubs/.

    Requires WORKFLOWS_BASE_URL and WORKFLOWS_TOKEN in the Infisical secrets cache.
    Self-hosted instances without those secrets skip silently.
    """
    result: dict = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0, "errors": []}

    # 1. Read credentials from Infisical cache
    cache_path = brain_path() / "_system" / "infisical_cache.json"
    cache = read_json(cache_path, default={})
    secrets = cache.get("secrets", {})
    base_url = secrets.get("WORKFLOWS_BASE_URL", "").rstrip("/")
    token = secrets.get("WORKFLOWS_TOKEN", "")

    if not base_url or not token:
        logger.debug(
            "Workflow auto-sync skipped: WORKFLOWS_BASE_URL/WORKFLOWS_TOKEN absent from Infisical cache"
        )
        return result

    # 2. Read stub files — keys drive what SHOULD exist
    stubs: dict[str, dict] = {}
    if STUBS_DIR.is_dir():
        for stub_file in sorted(STUBS_DIR.glob("*.stub.json")):
            try:
                stub = json.loads(stub_file.read_text())
                key = stub.get("key") or stub_file.stem.replace(".stub", "")
                stub["key"] = key
                stubs[key] = stub
            except Exception as exc:
                result["errors"].append(f"bad stub {stub_file.name}: {exc}")

    if not stubs:
        logger.debug("No workflow stubs found in %s", STUBS_DIR)
        return result

    # 3. Load current Brain automations index
    index_path = system_automations_path()
    records: list[dict] = read_json(index_path, default=[])
    existing: dict[str, dict] = {r["sync_key"]: r for r in records if r.get("auto_sync")}

    # 4. Create or update each stub's workflow
    for key, stub in stubs.items():
        try:
            wf_json, raw_text = _fetch_wf(base_url, token, key)
        except Exception as exc:
            logger.warning("Failed to fetch workflow '%s': %s", key, exc)
            result["errors"].append(f"fetch {key}: {exc}")
            continue

        new_hash = _content_hash(raw_text)

        if key in existing:
            rec = existing[key]
            if rec.get("content_hash") == new_hash:
                result["skipped"] += 1
                continue
            try:
                with _client() as c:
                    c.put(f"/api/v1/workflows/{rec['n8n_id']}", json=wf_json).raise_for_status()
            except Exception as exc:
                logger.warning("n8n update failed for '%s': %s", key, exc)
                result["errors"].append(f"update {key}: {exc}")
                continue
            for r in records:
                if r.get("sync_key") == key:
                    r["content_hash"] = new_hash
                    r["name"] = stub.get("name", r["name"])
                    r["tags"] = stub.get("tags", r.get("tags", []))
            result["updated"] += 1
            logger.info("Updated business workflow '%s'", key)
        else:
            try:
                with _client() as c:
                    resp = c.post("/api/v1/workflows", json=wf_json)
                    resp.raise_for_status()
                    n8n_data = resp.json()
            except Exception as exc:
                logger.warning("n8n import failed for '%s': %s", key, exc)
                result["errors"].append(f"import {key}: {exc}")
                continue
            new_record: dict = {
                "id": str(uuid4()),
                "n8n_id": str(n8n_data.get("id", "")),
                "name": stub.get("name") or wf_json.get("name", key),
                "scope": "business",
                "tags": stub.get("tags", []),
                "active": False,
                "auto_sync": True,
                "sync_key": key,
                "content_hash": new_hash,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_run": None,
            }
            records.append(new_record)
            result["created"] += 1
            logger.info("Created business workflow '%s'", key)

    # 5. Delete auto-synced records whose stub was removed from the repo
    orphans = [r for r in records if r.get("auto_sync") and r.get("sync_key") not in stubs]
    for rec in orphans:
        n8n_id = rec.get("n8n_id")
        if n8n_id:
            try:
                with _client() as c:
                    c.delete(f"/api/v1/workflows/{n8n_id}")
            except Exception as exc:
                logger.warning(
                    "Failed to delete orphaned workflow '%s' from n8n: %s", rec.get("name"), exc
                )
        records = [r for r in records if r["id"] != rec["id"]]
        result["deleted"] += 1
        logger.info("Deleted removed business workflow '%s'", rec.get("name"))

    write_json(index_path, records)
    logger.info("Business workflow auto-sync complete: %s", result)
    return result


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
