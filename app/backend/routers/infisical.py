from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from routers.auth import require_admin
from services import infisical_loader

router = APIRouter()


class TokenRequest(BaseModel):
    token: str


@router.get("/admin/infisical-status")
def get_infisical_status(_: dict = Depends(require_admin)):
    return infisical_loader.get_status()


@router.patch("/admin/infisical-token")
def update_infisical_token(req: TokenRequest, _: dict = Depends(require_admin)):
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token cannot be empty.")

    if not infisical_loader.validate_token(token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not connect to Infisical with this token. Check the token and INFISICAL_URL.",
        )

    infisical_loader.save_token_to_file(token)
    return {
        **infisical_loader.get_status(),
        "restart_required": True,
        "message": "Token saved. New secrets will load on next restart.",
    }


@router.delete("/admin/infisical-token", status_code=status.HTTP_200_OK)
def clear_infisical_token(_: dict = Depends(require_admin)):
    current = infisical_loader.get_status()
    if current["source"] == "env":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token is set via environment variable and cannot be cleared from the UI. Remove INFISICAL_TOKEN from your deploy config and restart.",
        )
    if not current["configured"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No token is configured.")

    infisical_loader.clear_token_file()
    return {"configured": False, "source": None, "message": "Token cleared. App will use local .env on next restart."}
