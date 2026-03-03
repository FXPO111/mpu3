from fastapi import APIRouter, Depends

from app.deps import require_program_access
from app.services.files import presign_upload

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/presign")
def presign(payload: dict, user=Depends(require_program_access)):
    _ = user
    return {"data": presign_upload(payload.get("filename", "document.pdf"))}