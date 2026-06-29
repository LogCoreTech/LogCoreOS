"""Brain export — lets a user download their entire brain folder as a zip."""
import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from routers.auth import get_current_user
from services.file_service import user_path
from services.rate_limiter import rate_limit

router = APIRouter()

_export_limit = rate_limit(2, 3600)  # 2 exports per hour — zip is CPU-intensive


@router.get("/export")
def export_brain(current_user: dict = Depends(get_current_user), _rl: None = Depends(_export_limit)):
    """Stream the current user's brain folder as a zip archive."""
    folder: Path = user_path(current_user["name"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if folder.exists():
            for f in folder.rglob("*"):
                if f.is_file() and f.name != "push_subscription.json":
                    zf.write(f, f.relative_to(folder))
    buf.seek(0)
    safe_name = current_user["name"].replace(" ", "_")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_brain.zip"'},
    )
