"""Assets module core router: asset tree CRUD (create/get/patch/delete/
archive/convert), bulk delete, contact cross-links, and file attachments.

Split out of one 1100+ line router.py into this file plus
router_templates.py / router_sharing.py / router_automation.py — the exact
precedent module_packages/finance/backend/ already established for this
same problem. manifest.py's `_get_router()` composes all four back into a
single router via `include_router()` calls, same as Finance's own six-way
composition.

Route order matters: this file's bare GET/PATCH/DELETE `/{asset_id}` routes
must never swallow a more specific static path (`/templates`, `/members`,
`/roles`, `/shares/respond`, `/automation/...`) declared in a sibling router
file — FastAPI/Starlette match routes in registration order, and a single
dynamic path segment matches any literal just as well. `_get_router()` in
manifest.py registers router_templates/router_automation/router_sharing
BEFORE this file's router for exactly that reason (this module's `/{asset_id}`
catch-all is the one thing Finance's own core router.py never had to work
around — every Finance route lives under a literal prefix like `/books/...`).

Shared helpers (`_validate_asset_id`, `_find_or_404`, `_is_admin`) live here
and are imported by the sibling router files, matching how Finance's own
sibling routers import `_find_or_404`/`_validate_id` from its router.py.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from routers.auth import get_workspace, require_admin, require_module
from services import assets_service
from services.rate_limiter import rate_limit

_require_assets = require_module("assets")
_write_limit = rate_limit(30, 60)

router = APIRouter()


def _validate_asset_id(asset_id: str) -> str:
    try:
        UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid asset ID format")
    return asset_id


def _find_or_404(current_user: dict, workspace: str, asset_id: str) -> dict:
    found = assets_service.find_asset(
        current_user["name"],
        workspace,
        asset_id,
        is_admin=current_user.get("role") == "admin",
        pool_edit=current_user.get("pool_edit") or [],
        viewer_role=current_user.get("feature_role") or "",
    )
    if found is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return found


def _is_admin(user: dict) -> bool:
    return user.get("role") == "admin"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class FieldDefModel(BaseModel):
    key: str = Field(..., max_length=40)
    label: str = Field("", max_length=80)
    type: str
    options: list[str] | None = None
    default: object | None = None


class AssetCreate(BaseModel):
    template: str | None = Field(None, max_length=40)
    template_id: str | None = Field(None, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    parent_id: str | None = None
    fields: dict = Field(default={})
    # A blank asset's own ad-hoc field definitions (2026-08-18) — same shape
    # a Template's `fields` use; only meaningful (and only ever consulted)
    # when no template/template_id is set.
    custom_field_defs: list[FieldDefModel] = Field(default=[], max_length=50)
    notes: str | None = Field(None, max_length=5000)
    tags: list[str] | None = None
    owner: str = Field("me", pattern="^(me|pool)$")


class AssetUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    parent_id: str | None = None
    fields: dict | None = None
    custom_field_defs: list[FieldDefModel] | None = Field(None, max_length=50)
    notes: str | None = Field(None, max_length=5000)
    tags: list[str] | None = None


class AttachTemplateRequest(BaseModel):
    template_id: str = Field(..., max_length=64)


class ConvertRequest(BaseModel):
    target: str = Field(..., pattern="^pool$")


class BulkDeleteRequest(BaseModel):
    ids: list[str]


# ---------------------------------------------------------------------------
# Assets (JWT; module-gated; workspace-scoped)
# ---------------------------------------------------------------------------


@router.get("")
def list_assets(
    template: str | None = None,
    include_archived: bool = False,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
):
    items = assets_service.list_visible(
        current_user["name"],
        workspace,
        include_archived=include_archived,
        is_admin=current_user.get("role") == "admin",
        pool_edit=current_user.get("pool_edit") or [],
        viewer_role=current_user.get("feature_role") or "",
    )
    if template:
        items = [a for a in items if a.get("template") == template]
    return assets_service.attach_templates(items)


@router.post("", status_code=201)
def create_asset(
    req: AssetCreate,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    creator_access, creator_caps = "edit", None
    if req.parent_id:
        # A child is created in its PARENT's store and inherits the parent's
        # audience — so anyone with edit access (or a contribute grant that
        # includes "children") can grow a shared subtree/"group".
        parent = _find_or_404(current_user, workspace, req.parent_id)
        parent_caps = parent.get("can_contribute") or {}
        if not parent["can_edit"] and "children" not in (parent_caps.get("add") or []):
            raise HTTPException(
                status_code=403, detail="Read-only access — cannot add under this asset"
            )
        store, store_ws = parent["store"], parent["store_workspace"]
        if not parent["can_edit"]:
            creator_access, creator_caps = "contribute", parent["can_contribute"]
    elif req.owner == "pool":
        pool_label = assets_service.POOL_LABEL[assets_service.POOL_USERS[workspace]]
        is_admin = current_user.get("role") == "admin"
        if not is_admin and pool_label not in (current_user.get("pool_edit") or []):
            raise HTTPException(
                status_code=403,
                detail="Pool asset creation requires admin or pool management rights",
            )
        store, store_ws = assets_service.POOL_USERS[workspace], "personal"
    else:
        store, store_ws = current_user["name"], workspace
    try:
        created = assets_service.create_asset(
            store,
            req.model_dump(exclude={"owner"}),
            workspace=store_ws,
            created_by=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Annotate like list/find responses when the record lives outside the
    # creator's own store. The frontend flips the create modal straight into
    # edit mode on this response and gates pool/share UI on _owner/_access —
    # a bare record made it treat a fresh pool asset as personal and send
    # shared_with on save (400 "use hidden_from instead of shares").
    if store in assets_service.POOL_LABEL:
        out = {**created, "_owner": assets_service.POOL_LABEL[store], "_access": creator_access}
    elif store != current_user["name"]:
        out = {**created, "_owner": store, "_access": creator_access}
    else:
        return created
    if creator_caps is not None:
        out["_caps"] = creator_caps
    return out


@router.get("/by-contact/{contact_id}")
def assets_by_contact(
    contact_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
):
    """Viewer-visible assets referencing this contact in a contact-type field.
    Feeds the contact References section."""
    return assets_service.list_assets_for_contact(
        current_user["name"],
        workspace,
        contact_id,
        is_admin=current_user.get("role") == "admin",
        pool_edit=current_user.get("pool_edit") or [],
        viewer_role=current_user.get("feature_role") or "",
    )


@router.get("/{asset_id}")
def get_asset(
    asset_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    asset = dict(found["asset"])
    if found["relation"] in ("pool", "shared"):
        asset["_owner"] = (
            assets_service.POOL_LABEL[found["store"]]
            if found["relation"] == "pool"
            else found["store"]
        )
        if found["can_edit"]:
            asset["_access"] = "edit"
        elif found.get("can_contribute"):
            asset["_access"] = "contribute"
            asset["_caps"] = found["can_contribute"]
        else:
            asset["_access"] = "read"
    asset["_template"] = assets_service.resolve_template(asset)
    return asset


@router.patch("/{asset_id}")
def update_asset(
    asset_id: str,
    req: AssetUpdate,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    updates = req.model_dump(exclude_unset=True)
    if not found["can_edit"]:
        # Contribute-level: only the field keys granted in the share/contributor
        # caps may change — never name/parent/notes.
        caps = found.get("can_contribute")
        if not caps:
            raise HTTPException(status_code=403, detail="Read-only access to this asset")
        allowed = set(caps.get("fields") or [])
        blocked = [k for k in updates if k != "fields"]
        bad_fields = [k for k in (updates.get("fields") or {}) if k not in allowed]
        if blocked or bad_fields:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Contribute access can only change these fields: "
                    + (", ".join(sorted(allowed)) or "none")
                ),
            )
    if found["relation"] == "shared" and ("parent_id" in updates):
        raise HTTPException(status_code=403, detail="Only the owner can move this asset")
    try:
        result = assets_service.update_asset(
            found["store"],
            asset_id,
            updates,
            workspace=found["store_workspace"],
            by=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return result


@router.post("/{asset_id}/attach-template")
def attach_template(
    asset_id: str,
    req: AttachTemplateRequest,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    """Second half of "Save as template" (2026-08-18, owner: "it also would
    need a convert to template button as well") — the frontend creates the
    Template first (a plain POST /assets/templates call, from the blank
    asset's own custom_field_defs), then calls this to attach it back onto
    the asset those defs came from. Self-service (edit access), not
    admin-only like /convert below — this never touches sharing/pool
    membership, just which template the caller's own asset now points at."""
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    if not found["can_edit"]:
        raise HTTPException(status_code=403, detail="Edit access required")
    try:
        result = assets_service.attach_template(
            found["store"],
            asset_id,
            req.template_id,
            workspace=found["store_workspace"],
            by=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return result


@router.post("/{asset_id}/archive")
def archive_asset(
    asset_id: str,
    cascade: bool = False,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    return _set_archived(asset_id, True, current_user, workspace, cascade)


@router.post("/{asset_id}/unarchive")
def unarchive_asset(
    asset_id: str,
    cascade: bool = False,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    return _set_archived(asset_id, False, current_user, workspace, cascade)


def _set_archived(asset_id: str, archived: bool, current_user: dict, workspace: str, cascade: bool):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    if not found["can_manage"]:
        raise HTTPException(status_code=403, detail="Only the owner or a pool manager can archive")
    return assets_service.set_archived(
        found["store"],
        asset_id,
        archived,
        workspace=found["store_workspace"],
        by=current_user["name"],
        cascade=cascade,
    )


@router.delete("/{asset_id}", status_code=204)
def delete_asset(
    asset_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    # Owners delete their own personal assets; pool assets stay admin-only.
    if not found["can_delete"]:
        raise HTTPException(status_code=403, detail="Only an admin can delete this asset")
    try:
        if not assets_service.delete_asset(
            found["store"],
            asset_id,
            workspace=found["store_workspace"],
            deleted_by=current_user["name"],
        ):
            raise HTTPException(status_code=404, detail="Asset not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/bulk-delete")
def bulk_delete_assets(
    req: BulkDeleteRequest,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    """UX Polish Batch #4 — assets_service.delete_asset() has no cascade at
    all (raises if the target still has children), unlike Notes' own
    delete_folder(). A same-request parent+child selection is resolved by
    depth: deepest (leaf) items first, so a child is already gone by the
    time its parent's own delete_asset() call runs."""
    is_admin = current_user.get("role") == "admin"
    pool_edit = current_user.get("pool_edit") or []
    viewer_role = current_user.get("feature_role") or ""

    resolved: list[tuple[str, dict]] = []
    failed: list[dict] = []
    for asset_id in req.ids:
        try:
            _validate_asset_id(asset_id)
        except HTTPException as exc:
            failed.append({"id": asset_id, "error": exc.detail})
            continue
        found = assets_service.find_asset(
            current_user["name"],
            workspace,
            asset_id,
            is_admin=is_admin,
            pool_edit=pool_edit,
            viewer_role=viewer_role,
        )
        if found is None:
            failed.append({"id": asset_id, "error": "Asset not found"})
            continue
        if not found["can_delete"]:
            failed.append({"id": asset_id, "error": "Only an admin can delete this asset"})
            continue
        resolved.append((asset_id, found))

    def _depth(found: dict) -> int:
        depth = 0
        current = found["asset"]
        seen = {current["id"]}
        while current.get("parent_id") and current["parent_id"] not in seen:
            parent_found = assets_service.find_asset(
                current_user["name"],
                workspace,
                current["parent_id"],
                is_admin=is_admin,
                pool_edit=pool_edit,
                viewer_role=viewer_role,
            )
            if parent_found is None:
                break
            current = parent_found["asset"]
            seen.add(current["id"])
            depth += 1
        return depth

    resolved.sort(key=lambda pair: _depth(pair[1]), reverse=True)

    deleted: list[str] = []
    for asset_id, found in resolved:
        try:
            if assets_service.delete_asset(
                found["store"],
                asset_id,
                workspace=found["store_workspace"],
                deleted_by=current_user["name"],
            ):
                deleted.append(asset_id)
            else:
                failed.append({"id": asset_id, "error": "Asset not found"})
        except ValueError as exc:
            failed.append({"id": asset_id, "error": str(exc)})
    return {"deleted": deleted, "failed": failed}


@router.post("/{asset_id}/convert")
def convert_asset(
    asset_id: str,
    req: ConvertRequest,
    current_user: dict = Depends(require_admin),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
    _assets: dict = Depends(_require_assets),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    if found["relation"] == "pool":
        raise HTTPException(status_code=400, detail="Asset is already a pool asset")
    try:
        return assets_service.convert_to_pool(
            found["store"], asset_id, workspace=found["store_workspace"], by=current_user["name"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


@router.post("/{asset_id}/files", status_code=201)
async def upload_attachment(
    asset_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_asset_id(asset_id)
    found = _find_or_404(current_user, workspace, asset_id)
    caps = found.get("can_contribute") or {}
    if not found["can_edit"] and "files" not in (caps.get("add") or []):
        raise HTTPException(status_code=403, detail="Read-only access to this asset")
    if (file.content_type or "") not in assets_service.ATTACHMENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type — images or PDF only")
    data = await file.read()
    try:
        return assets_service.add_attachment(
            found["store"],
            asset_id,
            file.filename or "",
            file.content_type or "",
            data,
            workspace=found["store_workspace"],
            by=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{asset_id}/files/{file_id}")
def get_attachment(
    asset_id: str,
    file_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
):
    from fastapi.responses import FileResponse

    _validate_asset_id(asset_id)
    _validate_asset_id(file_id)
    found = _find_or_404(current_user, workspace, asset_id)
    meta = assets_service.get_attachment(
        found["store"], asset_id, file_id, workspace=found["store_workspace"]
    )
    if meta is None:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(meta["path"]), media_type=meta["mime"], filename=meta["filename"])


@router.delete("/{asset_id}/files/{file_id}", status_code=204)
def delete_attachment(
    asset_id: str,
    file_id: str,
    current_user: dict = Depends(_require_assets),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    _validate_asset_id(asset_id)
    _validate_asset_id(file_id)
    found = _find_or_404(current_user, workspace, asset_id)
    if not found["can_edit"]:
        raise HTTPException(status_code=403, detail="Read-only access to this asset")
    if not assets_service.delete_attachment(
        found["store"],
        asset_id,
        file_id,
        workspace=found["store_workspace"],
        by=current_user["name"],
    ):
        raise HTTPException(status_code=404, detail="File not found")
