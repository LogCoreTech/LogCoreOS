"""Tests for the Brain export zip — routers/export.py.

Guards specifically against operational/credential files leaking into a
user's self-export: push_subscription.json and Finance/simplefin.json (the
SimpleFIN bank-access URL) are both meant to be admin/system-managed, never
bundled into a user's own portable data.
"""

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from routers.export import export_brain
from services import auth_service
from services.file_service import simplefin_path, user_path, write_json, write_markdown


@pytest.fixture()
def user(brain):
    return auth_service.create_user("alice@example.com", "password123", "Alice")


async def _export_namelist(current_user: dict) -> list[str]:
    response = export_brain(current_user, None)
    body = b""
    async for chunk in response.body_iterator:
        body += chunk if isinstance(chunk, bytes) else chunk.encode()
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        return zf.namelist()


@pytest.mark.asyncio
async def test_export_excludes_simplefin_credential(brain, user):
    write_markdown(user_path(user["name"]) / "Long_Term_Memory.md", "# Notes\n")
    write_json(simplefin_path(user["name"]), {"access_url": "https://bridge.simplefin.org/secret"})

    names = await _export_namelist(user)

    assert "Long_Term_Memory.md" in names
    assert str(Path("Finance") / "simplefin.json") not in names


@pytest.mark.asyncio
async def test_export_excludes_push_subscription(brain, user):
    write_markdown(user_path(user["name"]) / "Long_Term_Memory.md", "# Notes\n")
    write_json(user_path(user["name"]) / "push_subscription.json", {"endpoint": "https://..."})

    names = await _export_namelist(user)

    assert "push_subscription.json" not in names


@pytest.mark.asyncio
async def test_export_includes_ordinary_brain_files(brain, user):
    write_markdown(user_path(user["name"]) / "Long_Term_Memory.md", "# Notes\n")
    write_json(user_path(user["name"]) / "Tasks" / "tasks.json", {"tasks": []})

    names = await _export_namelist(user)

    assert "Long_Term_Memory.md" in names
    assert str(Path("Tasks") / "tasks.json") in names
