from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from routers.auth import require_admin
from services import features_service
from services.auth_service import get_user_by_id, update_user
from services.features_service import ALL_MODULE_IDS

router = APIRouter()

_PROTECTED_ROLES = {"member"}


class RoleModulesRequest(BaseModel):
    modules: dict[str, bool]

    @field_validator("modules")
    @classmethod
    def validate_module_ids(cls, v: dict) -> dict:
        invalid = [k for k in v if k not in ALL_MODULE_IDS]
        if invalid:
            raise ValueError(f"Unknown module IDs: {invalid}")
        return v


class CreateRoleRequest(BaseModel):
    name: str
    modules: dict[str, bool]

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Role name cannot be empty.")
        if v in _PROTECTED_ROLES or v == "admin":
            raise ValueError(f"'{v}' is a reserved role name.")
        if len(v) > 40:
            raise ValueError("Role name must be 40 characters or fewer.")
        return v

    @field_validator("modules")
    @classmethod
    def validate_module_ids(cls, v: dict) -> dict:
        invalid = [k for k in v if k not in ALL_MODULE_IDS]
        if invalid:
            raise ValueError(f"Unknown module IDs: {invalid}")
        return v


class FeatureRoleRequest(BaseModel):
    feature_role: str


@router.get("/admin/features")
def get_features(_: dict = Depends(require_admin)):
    return features_service.load_features()


@router.post("/admin/features/roles", status_code=status.HTTP_201_CREATED)
def create_role(req: CreateRoleRequest, _: dict = Depends(require_admin)):
    data = features_service.load_features()
    roles = data.get("roles", {})
    if req.name in roles:
        raise HTTPException(status_code=400, detail=f"Role '{req.name}' already exists.")
    # Fill in missing module defaults (True = enabled)
    full_map = {m: req.modules.get(m, True) for m in ALL_MODULE_IDS}
    roles[req.name] = full_map
    data["roles"] = roles
    features_service.save_features(data)
    return {"name": req.name, "modules": full_map}


@router.patch("/admin/features/roles/{role_name}")
def update_role(role_name: str, req: RoleModulesRequest, _: dict = Depends(require_admin)):
    data = features_service.load_features()
    roles = data.get("roles", {})
    if role_name not in roles:
        raise HTTPException(status_code=404, detail=f"Role '{role_name}' not found.")
    full_map = {m: req.modules.get(m, True) for m in ALL_MODULE_IDS}
    roles[role_name] = full_map
    data["roles"] = roles
    features_service.save_features(data)
    return {"name": role_name, "modules": full_map}


@router.delete("/admin/features/roles/{role_name}")
def delete_role(role_name: str, _: dict = Depends(require_admin)):
    if role_name in _PROTECTED_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"'{role_name}' is a built-in role and cannot be deleted.",
        )
    data = features_service.load_features()
    roles = data.get("roles", {})
    if role_name not in roles:
        raise HTTPException(status_code=404, detail=f"Role '{role_name}' not found.")
    del roles[role_name]
    data["roles"] = roles
    features_service.save_features(data)
    return {"deleted": role_name}


@router.patch("/admin/features/users/{user_id}/role")
def set_user_feature_role(
    user_id: str,
    req: FeatureRoleRequest,
    current_user: dict = Depends(require_admin),
):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Admins cannot change their own feature role.")

    data = features_service.load_features()
    roles = data.get("roles", {})
    if req.feature_role not in roles and req.feature_role != "member":
        raise HTTPException(status_code=400, detail=f"Role '{req.feature_role}' does not exist.")

    user = update_user(user_id, {"feature_role": req.feature_role})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True, "feature_role": req.feature_role}
