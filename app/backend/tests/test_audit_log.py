"""Coverage for the admin action audit log (2026-09-18, TASKS.md backlog
item: "user deletion, role changes, module toggles leave no queryable trail
today"). Covers the service directly (services/audit_log.py) and its wiring
into the three admin_users.py mutation points plus mod_store_service's
install/uninstall.

Note: the `brain` fixture itself calls mod_store_service.mark_installed()
for every LOCKED module (tasks/chat/dashboard) as part of its own setup —
now that mark_installed() writes an audit entry, every test using `brain`
starts with 3 pre-existing "module.install"/"test-fixture" entries already
in the log. Assertions below check the newest entries (index 0, 1, ...)
rather than an exact total count, since those 3 are always older than
anything a test itself records."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from routers.auth import UpdateRoleRequest, admin_delete_user, admin_get_audit_log
from routers.auth.admin_users import ModuleAccessRequest, update_user_modules
from services import audit_log, auth_service, mod_store_service

_ADMIN = {"id": "admin-1", "name": "Admin"}


def test_record_and_list_entries_newest_first(brain):
    audit_log.record(_ADMIN, "user.delete", "Bob", {"role": "member"})
    audit_log.record(_ADMIN, "module.install", "finance")

    entries = audit_log.list_entries()

    assert entries[0]["action"] == "module.install"  # most recent first
    assert entries[1]["action"] == "user.delete"
    assert entries[1]["actor"] == {"id": "admin-1", "name": "Admin"}
    assert entries[1]["details"] == {"role": "member"}


def test_list_entries_respects_limit(brain):
    for i in range(5):
        audit_log.record(_ADMIN, "user.role_change", f"user-{i}")

    assert len(audit_log.list_entries(limit=2)) == 2
    top5 = audit_log.list_entries(limit=5)
    assert [e["target"] for e in top5] == ["user-4", "user-3", "user-2", "user-1", "user-0"]


def test_entries_cap_keeps_only_the_most_recent(brain, monkeypatch):
    monkeypatch.setattr(audit_log, "_ENTRIES_CAP", 3)
    for i in range(5):
        audit_log.record(_ADMIN, "user.role_change", f"user-{i}")

    entries = audit_log.list_entries(limit=100)

    assert len(entries) == 3
    assert [e["target"] for e in entries] == ["user-4", "user-3", "user-2"]


def test_admin_delete_user_writes_an_audit_entry(brain):
    admin = auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")
    bob = auth_service.create_user("bob@example.com", "bobpass1", "Bob", role="member")

    admin_delete_user(bob["id"], admin)

    entries = audit_log.list_entries()
    assert entries[0]["action"] == "user.delete"
    assert entries[0]["target"] == "Bob"
    assert entries[0]["actor"]["name"] == "Admin"


def test_update_user_modules_writes_an_audit_entry(brain):
    admin = auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")
    bob = auth_service.create_user("bob@example.com", "bobpass1", "Bob", role="member")
    mod_store_service.mark_installed("finance", by="test-fixture")

    update_user_modules(bob["id"], ModuleAccessRequest(disabled_modules=["finance"]), admin)

    entries = audit_log.list_entries()
    assert entries[0]["action"] == "user.modules_change"
    assert entries[0]["target"] == "Bob"
    assert entries[0]["details"] == {"from": [], "to": ["finance"]}


def test_mod_store_install_writes_an_audit_entry(brain):
    mod_store_service.mark_installed("finance", by="Admin")

    entries = audit_log.list_entries()
    assert entries[0]["action"] == "module.install"
    assert entries[0]["target"] == "finance"
    assert entries[0]["actor"]["name"] == "Admin"


def test_mod_store_uninstall_writes_an_audit_entry(brain):
    mod_store_service.mark_installed("finance", by="Admin")
    mod_store_service.mark_uninstalled("finance", by="Admin")

    entries = audit_log.list_entries()
    assert entries[0]["action"] == "module.uninstall"
    assert entries[0]["target"] == "finance"


def test_admin_get_audit_log_endpoint_returns_entries(brain):
    admin = auth_service.create_user("admin@example.com", "adminpass1", "Admin", role="admin")
    audit_log.record(_ADMIN, "user.role_change", "Someone")

    result = admin_get_audit_log(limit=1, current_user=admin)

    assert len(result["entries"]) == 1
    assert result["entries"][0]["action"] == "user.role_change"
