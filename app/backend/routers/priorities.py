from fastapi import APIRouter, Depends

from routers.auth import get_current_user
from services.profile_service import get_priority_order

router = APIRouter()


@router.get("")
def get_priorities(current_user: dict = Depends(get_current_user)):
    return {"order": get_priority_order(current_user["name"])}
