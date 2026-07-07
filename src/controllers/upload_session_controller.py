import asyncio

from fastapi import APIRouter, Depends, File, Form, UploadFile

from src.auth import require_role, require_user
from src.enums.user_role import UserRole
from src.interfaces.upload_session_service import IUploadSessionService
from src.models.user import User
from src.schemas.upload_session import UploadSessionCreate, UploadSessionOut
from src.services.upload_session_service import get_upload_session_service
from src.services.upload_strategies._shared import read_upload

# Resumable uploads: open a session, PUT sequential chunks (pause/resume at
# will), then complete to run the ingestion pipeline. Same write gate as the
# regular upload endpoint: viewers cannot upload.
router = APIRouter(
    prefix="/documents/upload-sessions",
    tags=["documents"],
    dependencies=[Depends(require_user)],
)

_EDITOR_OR_ADMIN = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN))


@router.post(
    "",
    response_model=UploadSessionOut,
    summary="Open a resumable upload session",
    description=(
        "Declare the file name (extension decides how it will be ingested) and "
        "its exact size in bytes, then send the bytes with "
        "`PUT /documents/upload-sessions/{id}/chunk`."
    ),
)
async def create_upload_session(
    body: UploadSessionCreate,
    current_user: User = _EDITOR_OR_ADMIN,
    service: IUploadSessionService = Depends(get_upload_session_service),
):
    return service.create_session(
        body.file_name, body.total_size, current_user.id, body.category_id
    )


@router.get(
    "/{session_id}",
    response_model=UploadSessionOut,
    summary="Upload session status (where to resume from)",
    description="`next_offset` is the byte offset the next chunk must start at.",
)
async def get_upload_session(
    session_id: str,
    current_user: User = _EDITOR_OR_ADMIN,
    service: IUploadSessionService = Depends(get_upload_session_service),
):
    return service.get_status(session_id, current_user.id)


@router.put(
    "/{session_id}/chunk",
    response_model=UploadSessionOut,
    summary="Send the next chunk",
    description=(
        "`offset` must equal the session's current `bytes_received`; a mismatch "
        "returns 409 with the offset to resume from. Sending a chunk to a "
        "paused session resumes it."
    ),
)
async def upload_chunk(
    session_id: str,
    offset: int = Form(..., ge=0),
    chunk: UploadFile = File(...),
    current_user: User = _EDITOR_OR_ADMIN,
    service: IUploadSessionService = Depends(get_upload_session_service),
):
    data = await read_upload(chunk)
    return await asyncio.to_thread(
        service.append_chunk, session_id, current_user.id, offset, data
    )


@router.post(
    "/{session_id}/pause",
    response_model=UploadSessionOut,
    summary="Pause the upload",
)
async def pause_upload_session(
    session_id: str,
    current_user: User = _EDITOR_OR_ADMIN,
    service: IUploadSessionService = Depends(get_upload_session_service),
):
    return service.pause(session_id, current_user.id)


@router.post(
    "/{session_id}/complete",
    summary="Finish the upload and ingest the document",
    description=(
        "Requires every byte to have been received. Runs the same pipeline as "
        "`POST /documents/upload` (extraction, chunking, embeddings) and "
        "returns the created document/version."
    ),
)
async def complete_upload_session(
    session_id: str,
    current_user: User = _EDITOR_OR_ADMIN,
    service: IUploadSessionService = Depends(get_upload_session_service),
):
    # Heavy CPU work (extraction, embeddings) — keep the event loop free.
    result = await asyncio.to_thread(service.complete, session_id, current_user.id)
    return {"message": "Upload completed and document ingested.", **result}


@router.delete(
    "/{session_id}",
    summary="Abort the upload and discard received bytes",
)
async def abort_upload_session(
    session_id: str,
    current_user: User = _EDITOR_OR_ADMIN,
    service: IUploadSessionService = Depends(get_upload_session_service),
):
    service.abort(session_id, current_user.id)
    return {"message": "Upload session aborted."}
