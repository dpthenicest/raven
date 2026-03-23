from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import require_admin
from app.models.user import User
from app.services.nerc import parse_nerc_pdf

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/parse-nerc")
async def parse_nerc(
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    content = await file.read()
    feeders = parse_nerc_pdf(content)
    # TODO: validate and upsert feeders into DB
    return {"parsed": len(feeders), "message": "Parsing complete. Review and confirm before saving."}
