"""Instance-level automation API token (n8n → LogCore ingest/read access).

Stored in brain/_system/automations_config.json. Generated on first use; shown and
rotated from the Admin → n8n card. Shared by the assets automation API today and the
Automation Inbox later.
"""

import secrets

from services.file_service import brain_path, read_json, write_json


def _config_path():
    return brain_path() / "_system" / "automations_config.json"


def get_api_token() -> str:
    config = read_json(_config_path(), default={})
    token = config.get("api_token")
    if not token:
        token = secrets.token_urlsafe(32)
        config["api_token"] = token
        write_json(_config_path(), config)
    return token


def rotate_api_token() -> str:
    config = read_json(_config_path(), default={})
    config["api_token"] = secrets.token_urlsafe(32)
    write_json(_config_path(), config)
    return config["api_token"]


def verify_api_token(candidate: str) -> bool:
    return bool(candidate) and secrets.compare_digest(candidate, get_api_token())
