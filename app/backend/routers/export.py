"""Brain export — lets a user download their entire brain folder as a zip."""
import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from routers.auth import get_current_user
from services.file_service import user_path

router = APIRouter()


@router.get("/export")
def export_brain(current_user: dict = Depends(get_current_user)):
    """Stream the current user's brain folder as a zip archive."""
    folder: Path = user_path(current_user["name"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if folder.exists():
            for f in folder.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(folder))
    buf.seek(0)
    safe_name = current_user["name"].replace(" ", "_")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_brain.zip"'},
    )
