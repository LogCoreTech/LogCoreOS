"""POST /api/v1/contacts/intake/lead (router_intake.py) — lead intake via a
personal API key with the `leads:create` scope. The endpoint function is
called with the user dict require_api_key() itself resolves from a real key,
so the key → user → workspace → disabled-modules chain is exercised too."""

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from module_packages.contacts.backend.router_intake import LeadIntake, intake_lead
from routers.auth.deps import require_api_key
from services import api_key_service, auth_service
from services import contacts_service as crm
from services import rate_limiter as rl


@pytest.fixture(autouse=True)
def _clean_rate_limits():
    rl._hits.clear()
    yield
    rl._hits.clear()


@pytest.fixture()
def admin(brain):
    from services import mod_store_service

    mod_store_service.mark_installed("contacts", by="test")
    user = auth_service.create_user("owner@example.com", "password123", "Owner", role="admin")
    auth_service.update_user(user["id"], {"workspaces": ["personal", "business"]})
    return auth_service.get_user_by_id(user["id"])


def _key_user(admin, scopes=("leads:create",), workspace="personal", scope="leads:create"):
    _meta, key = api_key_service.create_key(admin, "Lead form", list(scopes), workspace, None)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=key)
    return require_api_key(scope)(creds)


def _lead(user, **kw):
    data = {"name": "Dana Smith", "phone": "(501) 555-0100", **kw}
    return intake_lead(LeadIntake(**data), user, None)


def test_first_lead_creates_contact_and_follow_up(admin):
    user = _key_user(admin)
    result = _lead(user, message="AC is blowing warm air", source="Website Form")
    assert result["created"] is True

    contact = crm.get_contact("Owner", "personal", result["contact_id"])
    assert contact["tags"] == ["website", "website-form"]
    assert contact["phones"][0]["number"] == "5015550100"
    assert contact["created_by"] == "api-key:Lead form"

    [interaction] = crm.list_interactions("Owner", "personal", result["contact_id"])
    assert interaction["summary"] == "[Website Form] AC is blowing warm air"
    expected = auth_service.today_for_user("Owner") + timedelta(days=1)
    assert interaction["follow_up"] == expected.isoformat()


def test_repeat_lead_from_same_phone_merges(admin):
    user = _key_user(admin)
    first = _lead(user, message="first")
    second = _lead(user, name="Dana S.", phone="+1 501 555 0100", message="second")
    assert second["contact_id"] == first["contact_id"]
    assert second["created"] is False
    assert len(crm.list_contacts("Owner", "personal")) == 1
    assert len(crm.list_interactions("Owner", "personal", first["contact_id"])) == 2


def test_same_name_different_phone_is_a_different_person(admin):
    user = _key_user(admin)
    first = _lead(user)
    second = _lead(user, phone="501-555-0199")
    assert second["contact_id"] != first["contact_id"]


def test_response_never_echoes_contact_data(admin):
    result = _lead(_key_user(admin), email="dana@example.com", message="private")
    assert set(result) == {"ok", "contact_id", "interaction_id", "created"}
    assert "dana" not in str(result).lower()


def test_key_without_scope_is_refused(admin):
    with pytest.raises(HTTPException) as exc:
        _key_user(admin, scopes=("mcp:read",))
    assert exc.value.status_code == 403


def test_contacts_not_installed_is_refused(admin):
    from services import mod_store_service

    mod_store_service.mark_uninstalled("contacts", by="test")
    with pytest.raises(HTTPException) as exc:
        _lead(_key_user(admin))
    assert exc.value.status_code == 403


def test_contacts_disabled_for_owner_is_refused(admin):
    auth_service.update_user(admin["id"], {"disabled_modules": ["contacts"]})
    user = _key_user(admin)
    with pytest.raises(HTTPException) as exc:
        _lead(user)
    assert exc.value.status_code == 403


def test_business_key_to_pool_lands_in_team_pool(admin):
    user = _key_user(admin, workspace="business")
    result = _lead(user, to_pool=True)
    assert crm.get_contact("_team", "business", result["contact_id"]) is not None
    assert crm.list_contacts("Owner", "business") == []


def test_follow_up_days_zero_is_today(admin):
    result = _lead(_key_user(admin), follow_up_days=0)
    [interaction] = crm.list_interactions("Owner", "personal", result["contact_id"])
    assert interaction["follow_up"] == auth_service.today_for_user("Owner").isoformat()


def test_invalid_email_is_a_400(admin):
    with pytest.raises(HTTPException) as exc:
        _lead(_key_user(admin), email="not-an-email")
    assert exc.value.status_code == 400
