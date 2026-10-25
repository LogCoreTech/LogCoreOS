"""POST /api/v1/contacts/intake/lead (router_intake.py) — lead intake via an
integration API key (`leads:create`), which belongs to the instance and is
pinned to one shared contacts list. The endpoint function is called with the
principal require_api_key() itself resolves from a real key, so the
key → principal chain is exercised too."""

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from module_packages.contacts.backend.router_intake import LeadIntake, _today, intake_lead
from routers.auth.deps import require_api_key
from services import api_key_service, auth_service
from services import contacts_service as crm
from services import mod_store_service
from services import rate_limiter as rl


@pytest.fixture(autouse=True)
def _clean_rate_limits():
    rl._hits.clear()
    yield
    rl._hits.clear()


@pytest.fixture()
def admin(brain):
    mod_store_service.mark_installed("contacts", by="test")
    user = auth_service.create_user("owner@example.com", "password123", "Owner", role="admin")
    auth_service.update_user(
        user["id"], {"workspaces": ["personal", "business"], "timezone": "America/Chicago"}
    )
    return auth_service.get_user_by_id(user["id"])


def _principal(admin, target="_team"):
    _meta, key = api_key_service.create_integration_key(admin, "Lead form", target, None)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=key)
    return require_api_key("leads:create")(creds)


def _lead(principal, **kw):
    data = {"name": "Dana Smith", "phone": "(501) 555-0100", **kw}
    return intake_lead(LeadIntake(**data), principal, None)


def test_first_lead_lands_in_the_keys_shared_list_with_follow_up(admin):
    result = _lead(_principal(admin), message="AC is blowing warm air", source="Website Form")
    assert result["created"] is True

    contact = crm.get_contact("_team", "business", result["contact_id"])
    assert contact["tags"] == ["website", "website-form"]
    assert contact["phones"][0]["number"] == "5015550100"
    assert contact["created_by"] == "api-key:Lead form"
    assert crm.list_contacts("Owner", "business") == []

    [interaction] = crm.list_interactions("_team", "business", result["contact_id"])
    assert interaction["summary"] == "[Website Form] AC is blowing warm air"
    expected = _today("America/Chicago") + timedelta(days=1)
    assert interaction["follow_up"] == expected.isoformat()


def test_household_target_lands_in_household(admin):
    result = _lead(_principal(admin, target="_household"))
    assert crm.get_contact("_household", "personal", result["contact_id"]) is not None


def test_repeat_lead_from_same_phone_merges(admin):
    principal = _principal(admin)
    first = _lead(principal, message="first")
    second = _lead(principal, name="Dana S.", phone="+1 501 555 0100", message="second")
    assert second["contact_id"] == first["contact_id"]
    assert second["created"] is False
    assert len(crm.list_contacts("_team", "business")) == 1
    assert len(crm.list_interactions("_team", "business", first["contact_id"])) == 2


def test_same_name_different_phone_is_a_different_person(admin):
    principal = _principal(admin)
    first = _lead(principal)
    second = _lead(principal, phone="501-555-0199")
    assert second["contact_id"] != first["contact_id"]


def test_response_never_echoes_contact_data(admin):
    result = _lead(_principal(admin), email="dana@example.com", message="private")
    assert set(result) == {"ok", "contact_id", "interaction_id", "created"}
    assert "dana" not in str(result).lower()


def test_keeps_working_after_creator_is_deleted(admin):
    _meta, key = api_key_service.create_integration_key(admin, "Form", "_team", None)
    auth_service.create_user("other@example.com", "password123", "Other", role="admin")
    auth_service.delete_user(admin["id"])
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=key)
    assert _lead(require_api_key("leads:create")(creds))["ok"] is True


def test_contacts_not_installed_is_refused(admin):
    principal = _principal(admin)
    mod_store_service.mark_uninstalled("contacts", by="test")
    with pytest.raises(HTTPException) as exc:
        _lead(principal)
    assert exc.value.status_code == 403


def test_follow_up_days_zero_is_today(admin):
    result = _lead(_principal(admin), follow_up_days=0)
    [interaction] = crm.list_interactions("_team", "business", result["contact_id"])
    assert interaction["follow_up"] == _today("America/Chicago").isoformat()


def test_invalid_email_is_a_400(admin):
    with pytest.raises(HTTPException) as exc:
        _lead(_principal(admin), email="not-an-email")
    assert exc.value.status_code == 400


def test_phone_without_enough_digits_is_a_400(admin):
    with pytest.raises(HTTPException) as exc:
        _lead(_principal(admin), phone="call me pls")
    assert exc.value.status_code == 400
    assert crm.list_contacts("_team", "business") == []


def test_bad_timezone_falls_back_to_utc():
    assert _today("Not/AZone") == _today("UTC")
