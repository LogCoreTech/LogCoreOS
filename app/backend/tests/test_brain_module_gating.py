"""Enforcement-gap tests for routers/brain.py: a module's owned_brain_paths
must be hidden from the generic Brain file browser when that module is
disabled for the viewer, and visible when it's enabled — bypass-confirmed-
then-closed pairs, not just "closed" assertions."""

from fastapi import HTTPException

from routers import brain as brain_router
from services.file_service import write_markdown, ws_path

_MANIFEST_SRC = """
from module_registry import ModuleManifest

def _get_router():
    from module_packages.t_brain_gate.backend.router import router
    return router

MODULE = ModuleManifest(
    id="t_brain_gate",
    display_name="Test",
    description="Test",
    icon="x",
    version="0.0.1",
    router_prefix="/api/v1/t_brain_gate",
    router_tags=["t_brain_gate"],
    get_router=_get_router,
    owned_brain_paths=["TestOwned"],
)
"""


def _user(name: str, disabled_modules: list[str]) -> dict:
    return {"name": name, "disabled_modules": disabled_modules}


def test_owned_path_hidden_from_listing_when_module_disabled(fake_module, brain):
    fake_module("t_brain_gate", _MANIFEST_SRC)
    base = ws_path("alice", "personal") / "TestOwned"
    base.mkdir(parents=True)
    write_markdown(base / "entry.md", "some data")

    listing = brain_router.list_files(_user("alice", ["t_brain_gate"]), workspace="personal")
    assert "TestOwned/entry.md" not in {f["path"] for f in listing}


def test_owned_path_visible_in_listing_when_module_enabled(fake_module, brain):
    fake_module("t_brain_gate", _MANIFEST_SRC)
    base = ws_path("alice", "personal") / "TestOwned"
    base.mkdir(parents=True)
    write_markdown(base / "entry.md", "some data")

    listing = brain_router.list_files(_user("alice", []), workspace="personal")
    assert "TestOwned/entry.md" in {f["path"] for f in listing}


def test_owned_path_read_blocked_when_module_disabled(fake_module, brain):
    fake_module("t_brain_gate", _MANIFEST_SRC)
    base = ws_path("alice", "personal") / "TestOwned"
    base.mkdir(parents=True)
    write_markdown(base / "entry.md", "some data")

    import pytest

    with pytest.raises(HTTPException) as exc:
        brain_router.get_file(
            "TestOwned/entry.md", _user("alice", ["t_brain_gate"]), workspace="personal"
        )
    assert exc.value.status_code == 403


def test_owned_path_read_allowed_when_module_enabled(fake_module, brain):
    fake_module("t_brain_gate", _MANIFEST_SRC)
    base = ws_path("alice", "personal") / "TestOwned"
    base.mkdir(parents=True)
    write_markdown(base / "entry.md", "some data")

    result = brain_router.get_file("TestOwned/entry.md", _user("alice", []), workspace="personal")
    assert result["content"] == "some data"


def test_owned_path_write_blocked_when_module_disabled(fake_module, brain):
    fake_module("t_brain_gate", _MANIFEST_SRC)
    base = ws_path("alice", "personal") / "TestOwned"
    base.mkdir(parents=True)
    write_markdown(base / "entry.md", "original")

    import pytest

    with pytest.raises(HTTPException) as exc:
        brain_router.save_file(
            "TestOwned/entry.md",
            brain_router.SaveRequest(content="hacked"),
            _user("alice", ["t_brain_gate"]),
            workspace="personal",
        )
    assert exc.value.status_code == 403
    assert (base / "entry.md").read_text() == "original"
