"""Contacts (CRM) module: contacts, interactions, deals, pipeline, custom fields,
asset-style sharing, CSV import/export, and a write-focused n8n automation API.

Access is resolved server-side via contacts_service.find_contact(); the frontend
never decides it. contribute = log interactions + create/advance deals only
(never edit core fields / delete / reshare) — enforced here.
"""

import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from routers.auth import get_current_user, get_workspace, require_admin, require_module
from services import auth_service, automations_config, contacts_service
from services.auth_service import get_user_by_name
from services.file_service import contact_photo_path
from services.rate_limiter import rate_limit

_ALLOWED_PHOTO_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
}
_PHOTO_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

_require_contacts = require_module("contacts")
_read_limit = rate_limit(60, 60)
_write_limit = rate_limit(30, 60)
_automation_limit = rate_limit(30, 60)

router = APIRouter()


def _validate_id(value: str, label: str = "ID") -> str:
    try:
        UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {label} format")
    return value


def _find_or_404(user: dict, workspace: str, contact_id: str):
    _validate_id(contact_id, "contact ID")
    found = contacts_service.find_contact(
        user["name"],
        user.get("feature_role", "member"),
        user.get("role") == "admin",
        workspace,
        contact_id,
    )
    if not found:
        raise HTTPException(status_code=404, detail="Contact not found")
    return found  # (store_user, contact, access)


def _require_edit(access: str) -> None:
    if access != "edit":
        raise HTTPException(status_code=403, detail="You don't have edit access to this contact.")


def _require_contribute(access: str) -> None:
    if access not in ("edit", "contribute"):
        raise HTTPException(status_code=403, detail="You can't add to this contact.")


def _effective_ws(contact: dict, workspace: str) -> str:
    """Self-contacts physically live in the personal store regardless of the
    active workspace tab — anchor all reads/writes of the contact's OWN data
    (record, interactions, deals, sharing) there so business-tab activity
    never fragments into an invisible parallel store."""
    return "personal" if contact.get("self_of") else workspace


# Profile fields merged in from the retired Profile module. "Basic" fields are
# just like any other Contact field (shareable); private ones are stripped for
# any non-owner viewer at the service layer regardless of what's set here.
# employer/industry/education/years_experience/skills now live inside
# career_history entries, not as flat fields — see contacts_service.py.
_PROFILE_BASIC_FIELDS = [
    "pronouns",
    "city",
    "state",
    "country",
    "occupation",
    "gender",
    "marital_status",
    "pets",
    "life_mission",
    "core_values",
    "key_constraints",
]
_PROFILE_PRIVATE_FIELDS = [
    "wake_weekday",
    "wake_weekend",
    "bedtime",
    "work_start",
    "work_end",
    "height_cm",
    "height_unit",
    "weight_kg",
    "weight_unit",
    "blood_type",
    "conditions",
    "medications",
    "diet",
    "exercise",
    "income_range",
    "budget_style",
    "communication_style",
    "tone",
    "response_language",
    "topics_to_emphasize",
    "topics_to_avoid",
]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ContactCreate(BaseModel):
    type: str = Field(default="person", pattern="^(person|company)$")
    name: str = Field(..., min_length=1, max_length=200)
    emails: list[str] | None = None
    phones: list[dict] | None = None
    address: str | None = None
    company_id: str | None = None
    tags: list[str] | None = None
    birthday: str | None = None
    status: str | None = None
    notes: str | None = None
    custom: dict | None = None
    pool: bool = False
    # Profile-merge fields — basic (shareable)
    pronouns: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    occupation: str | None = None
    gender: str | None = None
    marital_status: str | None = None
    pets: str | None = None
    life_mission: str | None = None
    core_values: str | None = None
    key_constraints: str | None = None
    priority_order: dict | None = None
    career_history: list[dict] | None = None
    # Profile-merge fields — private (never leave the owner's own view)
    wake_weekday: str | None = None
    wake_weekend: str | None = None
    bedtime: str | None = None
    work_start: str | None = None
    work_end: str | None = None
    height_cm: float | None = None
    height_unit: str | None = None
    weight_kg: float | None = None
    weight_unit: str | None = None
    blood_type: str | None = None
    conditions: str | None = None
    medications: str | None = None
    diet: str | None = None
    exercise: str | None = None
    income_range: str | None = None
    budget_style: str | None = None
    communication_style: str | None = None
    tone: str | None = None
    response_language: str | None = None
    topics_to_emphasize: str | None = None
    topics_to_avoid: str | None = None


class ContactUpdate(BaseModel):
    type: str | None = Field(default=None, pattern="^(person|company)$")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    emails: list[str] | None = None
    phones: list[dict] | None = None
    address: str | None = None
    company_id: str | None = None
    tags: list[str] | None = None
    birthday: str | None = None
    status: str | None = None
    notes: str | None = None
    custom: dict | None = None
    pronouns: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    occupation: str | None = None
    gender: str | None = None
    marital_status: str | None = None
    pets: str | None = None
    life_mission: str | None = None
    core_values: str | None = None
    key_constraints: str | None = None
    priority_order: dict | None = None
    career_history: list[dict] | None = None
    wake_weekday: str | None = None
    wake_weekend: str | None = None
    bedtime: str | None = None
    work_start: str | None = None
    work_end: str | None = None
    height_cm: float | None = None
    height_unit: str | None = None
    weight_kg: float | None = None
    weight_unit: str | None = None
    blood_type: str | None = None
    conditions: str | None = None
    medications: str | None = None
    diet: str | None = None
    exercise: str | None = None
    income_range: str | None = None
    budget_style: str | None = None
    communication_style: str | None = None
    tone: str | None = None
    response_language: str | None = None
    topics_to_emphasize: str | None = None
    topics_to_avoid: str | None = None


class InteractionCreate(BaseModel):
    type: str = Field(default="note", pattern="^(call|email|meeting|text|note)$")
    summary: str = Field(default="", max_length=5000)
    date: str | None = None
    follow_up: str | None = None


class InteractionUpdate(BaseModel):
    summary: str | None = Field(default=None, max_length=5000)
    follow_up: str | None = None
    follow_up_done: bool | None = None


class DealCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    value_cents: int = 0
    stage: str | None = None
    expected_close: str | None = None
    follow_up: str | None = None
    notes: str | None = None


class DealUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    value_cents: int | None = None
    stage: str | None = None
    expected_close: str | None = None
    follow_up: str | None = None
    notes: str | None = None
    invoice_id: str | None = None


class DealAssetLink(BaseModel):
    asset_id: str = Field(..., min_length=1, max_length=64)


class ShareEntry(BaseModel):
    target: str = Field(..., min_length=1, max_length=80)
    access: str = Field(default="read", pattern="^(read|contribute|edit)$")


class AccessRequest(BaseModel):
    shared_with: list[ShareEntry] | None = Field(default=None, max_length=50)
    hidden_from: list[str] | None = Field(default=None, max_length=50)
    contributors: list[ShareEntry] | None = Field(default=None, max_length=50)


class ShareRespond(BaseModel):
    notif_id: str
    accept: bool


class PipelineUpdate(BaseModel):
    stages: list[str] = Field(..., max_length=20)


class FieldsUpdate(BaseModel):
    fields: list[dict] = Field(default=[], max_length=40)


# ---------------------------------------------------------------------------
# Contacts CRUD
# ---------------------------------------------------------------------------


@router.get("")
def list_contacts(
    include_archived: bool = Query(default=False),
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    return contacts_service.list_visible_contacts(
        current_user["name"],
        current_user.get("feature_role", "member"),
        current_user.get("role") == "admin",
        workspace,
        include_archived,
    )


@router.post("")
def create_contact(
    req: ContactCreate,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user = current_user["name"]
    if req.pool:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins create shared-pool contacts")
        store_user = contacts_service.pool_for(workspace)
    data = req.model_dump(exclude={"pool"})
    try:
        contact = contacts_service.create_contact(
            store_user, workspace, data, created_by=current_user["name"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return contacts_service.annotate(contact, store_user, current_user["name"], "edit")


@router.get("/members")
def list_members(
    current_user: dict = Depends(_require_contacts),
    _rl: None = Depends(_read_limit),
):
    return [{"name": u["name"]} for u in auth_service.list_users()]


@router.get("/roles")
def list_roles(
    current_user: dict = Depends(_require_contacts),
    _rl: None = Depends(_read_limit),
):
    from services.features_service import load_features

    return sorted((load_features().get("roles") or {}).keys())


@router.get("/fields")
def get_fields(
    current_user: dict = Depends(_require_contacts),
    _rl: None = Depends(_read_limit),
):
    return contacts_service.get_custom_fields()


@router.put("/fields")
def set_fields(
    req: FieldsUpdate,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    return contacts_service.set_custom_fields(req.fields)


@router.get("/pipeline")
def get_pipeline(
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    return {"stages": contacts_service.get_pipeline(current_user["name"], workspace)}


@router.put("/pipeline")
def set_pipeline(
    req: PipelineUpdate,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    return {"stages": contacts_service.set_pipeline(current_user["name"], workspace, req.stages)}


@router.get("/export/csv", response_class=PlainTextResponse)
def export_csv(
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    contacts = contacts_service.list_visible_contacts(
        current_user["name"],
        current_user.get("feature_role", "member"),
        current_user.get("role") == "admin",
        workspace,
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["name", "type", "emails", "phones", "address", "tags", "status", "notes"])
    for c in contacts:
        writer.writerow(
            [
                c.get("name", ""),
                c.get("type", ""),
                "; ".join(c.get("emails", [])),
                "; ".join(c.get("phones", [])),
                c.get("address", ""),
                "; ".join(c.get("tags", [])),
                c.get("status", ""),
                c.get("notes", ""),
            ]
        )
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")


class CsvCommit(BaseModel):
    rows: list[dict] = Field(default=[], max_length=2000)


@router.post("/import/csv")
def import_csv_preview(
    file: UploadFile = File(...),
    current_user: dict = Depends(_require_contacts),
    _rl: None = Depends(_write_limit),
):
    raw = file.file.read(5 * 1024 * 1024)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 CSV")
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(r) for r in reader][:2000]
    return {"headers": reader.fieldnames or [], "rows": rows[:20], "total_rows": len(rows)}


@router.post("/import/csv/commit")
def import_csv_commit(
    req: CsvCommit,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    """Simple column-name import: name / email / phone / tags (dedup by name/email)."""
    store = current_user["name"]
    created, skipped = 0, 0
    for row in req.rows:
        name = (row.get("name") or row.get("Name") or "").strip()
        email = (row.get("email") or row.get("Email") or "").strip()
        if not name:
            skipped += 1
            continue
        if contacts_service.find_match(store, workspace, name=name, email=email):
            skipped += 1
            continue
        data = {"name": name, "type": "person"}
        if email:
            data["emails"] = [email]
        phone = (row.get("phone") or row.get("Phone") or "").strip()
        if phone:
            data["phones"] = [phone]
        tags = (row.get("tags") or row.get("Tags") or "").strip()
        if tags:
            data["tags"] = [t.strip() for t in tags.replace(";", ",").split(",") if t.strip()]
        try:
            contacts_service.create_contact(store, workspace, data, created_by=store)
            created += 1
        except ValueError:
            skipped += 1
    return {"created": created, "skipped": skipped}


@router.get("/me")
def get_my_contact(
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_read_limit),
):
    """The caller's own self-contact — gated by login only, NOT the contacts
    module. Profile had no module gate before this merge (every authenticated
    user, including guests with contacts disabled by default, could use it);
    this preserves that so nobody loses their own profile because Contacts is
    disabled for them. All other contact features stay module-gated."""
    contact = contacts_service.get_self_contact(current_user["name"], create_if_missing=True)
    return contacts_service.annotate(contact, current_user["name"], current_user["name"], "edit")


@router.patch("/me")
def update_my_contact(
    req: ContactUpdate,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_write_limit),
):
    contact = contacts_service.get_self_contact(current_user["name"], create_if_missing=True)
    try:
        updated = contacts_service.update_contact(
            current_user["name"], "personal", contact["id"], req.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return contacts_service.annotate(updated, current_user["name"], current_user["name"], "edit")


@router.post("/{contact_id}/affiliations/{other_id}")
def link_affiliation(
    contact_id: str,
    other_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    try:
        updated, _other = contacts_service.link_affiliation(
            current_user["name"],
            current_user.get("feature_role", "member"),
            current_user.get("role") == "admin",
            workspace,
            contact_id,
            other_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return updated


@router.delete("/{contact_id}/affiliations/{other_id}")
def unlink_affiliation(
    contact_id: str,
    other_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    try:
        updated, _other = contacts_service.unlink_affiliation(
            current_user["name"],
            current_user.get("feature_role", "member"),
            current_user.get("role") == "admin",
            workspace,
            contact_id,
            other_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return updated


@router.get("/{contact_id}")
def get_contact(
    contact_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    return contacts_service.annotate(contact, store_user, current_user["name"], access)


@router.patch("/{contact_id}")
def update_contact(
    contact_id: str,
    req: ContactUpdate,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_edit(access)
    ws = _effective_ws(contact, workspace)
    try:
        updated = contacts_service.update_contact(
            store_user,
            ws,
            contact_id,
            req.model_dump(exclude_unset=True),
            viewer=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return contacts_service.annotate(updated, store_user, current_user["name"], "edit")


@router.post("/{contact_id}/archive")
def archive_contact(
    contact_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_edit(access)
    try:
        contacts_service.set_archived(
            store_user, _effective_ws(contact, workspace), contact_id, True
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.post("/{contact_id}/unarchive")
def unarchive_contact(
    contact_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_edit(access)
    contacts_service.set_archived(store_user, _effective_ws(contact, workspace), contact_id, False)
    return {"ok": True}


@router.delete("/{contact_id}")
def delete_contact(
    contact_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    if contacts_service.is_pool(store_user):
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins delete pool contacts")
    else:
        _require_edit(access)
    try:
        contacts_service.delete_contact(store_user, _effective_ws(contact, workspace), contact_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Photo — shows at the top of the card in place of the type/gender icon
# ---------------------------------------------------------------------------


@router.post("/{contact_id}/photo")
async def upload_contact_photo(
    contact_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_edit(access)
    ext = _ALLOWED_PHOTO_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(
            status_code=400, detail="Only JPEG, PNG, WebP, or AVIF images are allowed"
        )
    data = await file.read()
    if len(data) > _PHOTO_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Image must be under 5 MB")
    ws = _effective_ws(contact, workspace)
    updated = contacts_service.set_contact_photo(store_user, ws, contact_id, ext)
    if updated is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    photo_path = contact_photo_path(store_user, ws, contact_id, ext)
    photo_path.parent.mkdir(parents=True, exist_ok=True)
    photo_path.write_bytes(data)
    return {"ok": True}


@router.get("/{contact_id}/photo")
def get_contact_photo(
    contact_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, contact, _access = _find_or_404(current_user, workspace, contact_id)
    ext = contact.get("photo_ext")
    if not ext:
        raise HTTPException(status_code=404, detail="No photo uploaded")
    path = contact_photo_path(store_user, _effective_ws(contact, workspace), contact_id, ext)
    if not path.exists():
        raise HTTPException(status_code=404, detail="No photo uploaded")
    mime = {v: k for k, v in _ALLOWED_PHOTO_TYPES.items()}.get(ext, "application/octet-stream")
    return FileResponse(str(path), media_type=mime)


@router.delete("/{contact_id}/photo", status_code=204)
def delete_contact_photo(
    contact_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_edit(access)
    contacts_service.clear_contact_photo(store_user, _effective_ws(contact, workspace), contact_id)


# ---------------------------------------------------------------------------
# Interactions
# ---------------------------------------------------------------------------


@router.get("/{contact_id}/interactions")
def list_interactions(
    contact_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, contact, _access = _find_or_404(current_user, workspace, contact_id)
    return contacts_service.list_interactions(
        store_user, _effective_ws(contact, workspace), contact_id
    )


@router.post("/{contact_id}/interactions")
def add_interaction(
    contact_id: str,
    req: InteractionCreate,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_contribute(access)
    try:
        return contacts_service.add_interaction(
            store_user,
            _effective_ws(contact, workspace),
            contact_id,
            req.model_dump(),
            created_by=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{contact_id}/interactions/{interaction_id}")
def update_interaction(
    contact_id: str,
    interaction_id: str,
    req: InteractionUpdate,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_contribute(access)
    updated = contacts_service.update_interaction(
        store_user,
        _effective_ws(contact, workspace),
        interaction_id,
        req.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Interaction not found")
    return updated


@router.delete("/{contact_id}/interactions/{interaction_id}")
def delete_interaction(
    contact_id: str,
    interaction_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_edit(access)
    ws = _effective_ws(contact, workspace)
    if not contacts_service.delete_interaction(store_user, ws, interaction_id):
        raise HTTPException(status_code=404, detail="Interaction not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------------


@router.get("/{contact_id}/deals")
def list_deals(
    contact_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, contact, _access = _find_or_404(current_user, workspace, contact_id)
    return contacts_service.list_deals(store_user, _effective_ws(contact, workspace), contact_id)


@router.post("/{contact_id}/deals")
def add_deal(
    contact_id: str,
    req: DealCreate,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_contribute(access)
    try:
        return contacts_service.add_deal(
            store_user,
            _effective_ws(contact, workspace),
            contact_id,
            req.model_dump(),
            created_by=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{contact_id}/deals/{deal_id}")
def update_deal(
    contact_id: str,
    deal_id: str,
    req: DealUpdate,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_contribute(access)
    try:
        updated = contacts_service.update_deal(
            store_user,
            _effective_ws(contact, workspace),
            deal_id,
            req.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Deal not found")
    return updated


@router.delete("/{contact_id}/deals/{deal_id}")
def delete_deal(
    contact_id: str,
    deal_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_edit(access)
    if not contacts_service.delete_deal(store_user, _effective_ws(contact, workspace), deal_id):
        raise HTTPException(status_code=404, detail="Deal not found")
    return {"ok": True}


@router.get("/deals/{deal_id}")
def get_deal_by_id(
    deal_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    """Deal lookup by id alone — used by Finance surfaces (invoice/tx context
    chips) that only hold a deal_id. Access inherits from the parent contact."""
    _validate_id(deal_id, "deal ID")
    found = contacts_service.find_deal(
        current_user["name"],
        current_user.get("feature_role", "member"),
        current_user.get("role") == "admin",
        workspace,
        deal_id,
    )
    if not found:
        raise HTTPException(status_code=404, detail="Deal not found")
    _store_user, deal, contact, access = found
    return {
        **deal,
        "_access": access,
        "_contact_id": contact["id"],
        "_contact_name": contact.get("name", ""),
    }


@router.post("/{contact_id}/deals/{deal_id}/assets")
def link_deal_asset(
    contact_id: str,
    deal_id: str,
    req: DealAssetLink,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    """Link an existing Asset to a deal. Contribute-level (same bucket as deal
    create/advance). Read access on the asset is enough — the gated write is
    the deal mutation, not the asset."""
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_contribute(access)
    from services import assets_service

    found = assets_service.find_asset(
        current_user["name"],
        workspace,
        req.asset_id,
        is_admin=current_user.get("role") == "admin",
        pool_edit=current_user.get("pool_edit") or [],
        viewer_role=current_user.get("feature_role", "member"),
    )
    if found is None:
        raise HTTPException(status_code=404, detail="Asset not found or not visible to you")
    updated = contacts_service.link_asset(
        store_user, _effective_ws(contact, workspace), deal_id, req.asset_id
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return updated


@router.delete("/{contact_id}/deals/{deal_id}/assets/{asset_id}")
def unlink_deal_asset(
    contact_id: str,
    deal_id: str,
    asset_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_contribute(access)
    updated = contacts_service.unlink_asset(
        store_user, _effective_ws(contact, workspace), deal_id, asset_id
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return updated


# ---------------------------------------------------------------------------
# Contact money view (cross-module read, scoped to the viewer's finance access)
# ---------------------------------------------------------------------------


@router.get("/{contact_id}/finance")
def contact_finance(
    contact_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    """Money references for this contact — payee totals, invoices billing them,
    and per-deal job profit — drawn ONLY from finance books the viewer can
    access (personal books stay invisible to others)."""
    store_user, contact, _access = _find_or_404(current_user, workspace, contact_id)
    if "finance" in (current_user.get("disabled_modules") or []):
        return {"available": False}
    from services import finance_invoice_service, finance_service

    viewer = current_user["name"]
    viewer_role = current_user.get("feature_role", "member")
    is_admin = current_user.get("role") == "admin"

    spent, received, tx_count = 0, 0, 0
    invoices_out: list[dict] = []
    invoices_total, outstanding = 0, 0
    try:
        books = finance_service.list_visible_books(viewer, viewer_role, is_admin, workspace)
        for b in books:
            store = finance_service.store_for_annotated(b, viewer, workspace)
            txs, _total = finance_service.list_transactions(store, workspace, b["id"])
            for t in txs:
                if t.get("payee_contact_id") == contact_id:
                    tx_count += 1
                    if t.get("amount_cents", 0) < 0:
                        spent += -t["amount_cents"]
                    else:
                        received += t["amount_cents"]
            # Invoice data follows the see_balances rule (mirrors _require_full_read)
            if b.get("_access") == "contribute" and not (b.get("_caps") or {}).get("see_balances"):
                continue
            client_ids = {
                c["id"]
                for c in finance_invoice_service.list_clients(store, workspace, b["id"])
                if c.get("contact_id") == contact_id
            }
            if not client_ids:
                continue
            for inv in finance_invoice_service.list_invoices(store, workspace, b["id"]):
                if inv.get("client_id") not in client_ids:
                    continue
                invoices_out.append({**inv, "book_id": b["id"], "book_name": b["name"]})
                if inv.get("status") != "void":
                    invoices_total += inv.get("total_cents", 0)
                    if inv.get("status") == "sent":
                        outstanding += inv.get("balance_cents", 0)
    except Exception:
        pass

    # Per-deal job profit: invoiced/collected from deal-billed invoices,
    # expenses from the deal's linked assets — all viewer-scoped.
    deals_out: list[dict] = []
    try:
        for deal in contacts_service.list_deals(
            store_user, _effective_ws(contact, workspace), contact_id
        ):
            d_invs = finance_invoice_service.list_invoices_for_deal(
                viewer, viewer_role, is_admin, workspace, deal["id"]
            )
            live = [i for i in d_invs if i.get("status") != "void"]
            expenses = 0
            for aid in deal.get("linked_asset_ids") or []:
                for t in finance_service.list_transactions_for_asset(
                    viewer, viewer_role, is_admin, workspace, aid
                ):
                    if t.get("amount_cents", 0) < 0:
                        expenses += -t["amount_cents"]
            collected = sum(i.get("paid_cents", 0) for i in live)
            deals_out.append(
                {
                    "deal_id": deal["id"],
                    "title": deal.get("title", ""),
                    "invoiced_cents": sum(i.get("total_cents", 0) for i in live),
                    "collected_cents": collected,
                    "expenses_cents": expenses,
                    "net_cents": collected - expenses,
                }
            )
    except Exception:
        pass

    return {
        "available": True,
        "spent_cents": spent,
        "received_cents": received,
        "tx_count": tx_count,
        "invoices_total_cents": invoices_total,
        "outstanding_cents": outstanding,
        "invoices": invoices_out,
        "deals": deals_out,
    }


# ---------------------------------------------------------------------------
# Sharing
# ---------------------------------------------------------------------------


def _require_owner_or_pool_admin(current_user: dict, store_user: str) -> None:
    if contacts_service.is_pool(store_user):
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins manage pool contacts")
    elif store_user != current_user["name"]:
        raise HTTPException(status_code=403, detail="Only the owner can change sharing")


def _notify_share_requests(owner: str, workspace: str, contact: dict, users: list[str]) -> None:
    try:
        from services.suggestions_service import notify_user

        for name in users:
            notify_user(
                name,
                "👥 Contact shared with you",
                f"{owner} wants to share the contact “{contact['name']}” with you.",
                source="contacts",
                action={
                    "type": "contacts_share",
                    "owner": owner,
                    "workspace": workspace,
                    "contact_id": contact["id"],
                },
                url="/contacts",
            )
    except Exception:
        pass


@router.put("/{contact_id}/access")
def update_contact_access(
    contact_id: str,
    req: AccessRequest,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, _access = _find_or_404(current_user, workspace, contact_id)
    _require_owner_or_pool_admin(current_user, store_user)
    ws = _effective_ws(contact, workspace)
    try:
        record, to_notify = contacts_service.update_access(
            store_user,
            ws,
            contact_id,
            shared_with=(
                [e.model_dump() for e in req.shared_with] if req.shared_with is not None else None
            ),
            hidden_from=req.hidden_from,
            contributors=(
                [e.model_dump() for e in req.contributors] if req.contributors is not None else None
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _notify_share_requests(store_user, ws, contact, to_notify)
    return contacts_service.annotate(record, store_user, current_user["name"], "edit")


@router.post("/shares/respond")
def respond_share(
    req: ShareRespond,
    current_user: dict = Depends(_require_contacts),
    _rl: None = Depends(_write_limit),
):
    from services import suggestions_service

    notif = suggestions_service.resolve_notification(current_user["name"], req.notif_id)
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    action = notif.get("action") or {}
    if action.get("type") != "contacts_share":
        raise HTTPException(status_code=400, detail="Not a contact share request")
    contacts_service.respond_share(
        current_user["name"],
        action.get("owner", ""),
        action.get("workspace", "personal"),
        action.get("contact_id", ""),
        req.accept,
    )
    return {"ok": True}


@router.post("/{contact_id}/leave")
def leave_contact(
    contact_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, _contact, _access = _find_or_404(current_user, workspace, contact_id)
    if store_user == current_user["name"] or contacts_service.is_pool(store_user):
        raise HTTPException(status_code=400, detail="You can only leave a contact shared with you")
    contacts_service.respond_share(
        current_user["name"], store_user, workspace, contact_id, accept=False
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Automation API (n8n) — X-Automation-Token, write-focused, NO bulk export
# ---------------------------------------------------------------------------


def _require_automation_token(x_automation_token: str = Header("")) -> None:
    if not automations_config.verify_api_token(x_automation_token):
        raise HTTPException(status_code=401, detail="Invalid automation token")


def _automation_store(user: str, workspace: str) -> tuple[str, str]:
    if user in ("_team", "_household"):
        return user, "personal"
    if get_user_by_name(user) is None:
        raise HTTPException(status_code=404, detail=f"Unknown user {user!r}")
    return user, workspace


class AutoContact(BaseModel):
    user: str
    workspace: str = "personal"
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(default="person", pattern="^(person|company)$")
    emails: list[str] | None = None
    phones: list[str] | None = None
    tags: list[str] | None = None
    notes: str | None = None
    external_id: str | None = None


@router.get("/automation/lookup")
def automation_lookup(
    user: str,
    workspace: str = "personal",
    email: str = "",
    name: str = "",
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    """Single-contact dedup lookup. Deliberately NOT a list/export endpoint —
    a leaked token cannot dump the contact base."""
    store, store_ws = _automation_store(user, workspace)
    match = contacts_service.find_match(store, store_ws, name=name, email=email)
    return {"found": bool(match), "contact_id": match["id"] if match else None}


@router.post("/automation/contacts")
def automation_upsert_contact(
    req: AutoContact,
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    store, store_ws = _automation_store(req.user, req.workspace)
    existing = contacts_service.find_match(
        store, store_ws, name=req.name, email=(req.emails or [""])[0]
    )
    data = req.model_dump(exclude={"user", "workspace", "external_id"})
    try:
        if existing:
            contact = contacts_service.update_contact(store, store_ws, existing["id"], data)
        else:
            contact = contacts_service.create_contact(
                store, store_ws, data, created_by="automation"
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": contact["id"], "created": existing is None}


class AutoInteraction(BaseModel):
    user: str
    workspace: str = "personal"
    contact_id: str
    type: str = Field(default="note", pattern="^(call|email|meeting|text|note)$")
    summary: str = Field(default="", max_length=5000)
    date: str | None = None
    follow_up: str | None = None


@router.post("/automation/interactions")
def automation_add_interaction(
    req: AutoInteraction,
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    store, store_ws = _automation_store(req.user, req.workspace)
    if not contacts_service.get_contact(store, store_ws, req.contact_id):
        raise HTTPException(status_code=404, detail="Contact not found")
    try:
        return contacts_service.add_interaction(
            store, store_ws, req.contact_id, req.model_dump(), created_by="automation"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class AutoDeal(BaseModel):
    user: str
    workspace: str = "personal"
    contact_id: str
    title: str = Field(..., min_length=1, max_length=120)
    value_cents: int = 0
    stage: str | None = None


@router.post("/automation/deals")
def automation_add_deal(
    req: AutoDeal,
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    store, store_ws = _automation_store(req.user, req.workspace)
    if not contacts_service.get_contact(store, store_ws, req.contact_id):
        raise HTTPException(status_code=404, detail="Contact not found")
    try:
        return contacts_service.add_deal(
            store, store_ws, req.contact_id, req.model_dump(), created_by="automation"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
