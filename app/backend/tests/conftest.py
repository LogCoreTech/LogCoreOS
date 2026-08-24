"""Shared fixtures for all backend tests."""

import shutil
import sys
from pathlib import Path

# Add app/backend to sys.path so imports resolve without package install
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


@pytest.fixture()
def brain(tmp_path, monkeypatch):
    """Patch settings.brain_path to an isolated temp directory."""
    from config import settings

    monkeypatch.setattr(settings, "brain_path", tmp_path / "brain")
    (tmp_path / "brain" / "_system").mkdir(parents=True, exist_ok=True)
    return tmp_path / "brain"


_MODULE_PACKAGES_DIR = Path(__file__).parent.parent / "module_packages"


@pytest.fixture()
def fake_module():
    """Write a real module_packages/<id>/ package to disk for the duration of
    one test, then remove it and purge it from sys.modules. Returns a
    make(module_id, manifest_src, router_src=None, dashboard_block_src=None,
    agent_tools_src=None) callable — call it once per fake module a test
    needs; cleanup handles all of them.

    module_packages/ must be a REAL importable package (its own code, e.g. a
    module's get_router callable, imports sibling files via normal dotted
    imports), so this writes real files rather than mocking importlib —
    exercising the actual discovery/import path a test needs confidence in.
    """
    created_ids: list[str] = []

    def make(
        module_id: str,
        manifest_src: str,
        router_src: str | None = None,
        dashboard_block_src: str | None = None,
        agent_tools_src: str | None = None,
    ) -> Path:
        pkg_dir = _MODULE_PACKAGES_DIR / module_id
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "manifest.py").write_text(manifest_src)

        backend_dir = pkg_dir / "backend"
        backend_dir.mkdir(exist_ok=True)
        (backend_dir / "__init__.py").write_text("")
        (backend_dir / "router.py").write_text(
            router_src
            or "from fastapi import APIRouter\nrouter = APIRouter()\n"
            "@router.get('/ping')\ndef ping():\n    return {'ok': True}\n"
        )
        if dashboard_block_src:
            (backend_dir / "dashboard_block.py").write_text(dashboard_block_src)
        if agent_tools_src:
            (backend_dir / "agent_tools.py").write_text(agent_tools_src)

        created_ids.append(module_id)
        return pkg_dir

    yield make

    for module_id in created_ids:
        shutil.rmtree(_MODULE_PACKAGES_DIR / module_id, ignore_errors=True)
        for name in list(sys.modules):
            if name == f"module_packages.{module_id}" or name.startswith(
                f"module_packages.{module_id}."
            ):
                del sys.modules[name]
