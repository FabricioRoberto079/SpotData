import logging

from fastapi import Depends
from sqlalchemy.orm import Session

from src.data.postgres_client import get_session
from src.enums.upload_session_status import UploadSessionStatus
from src.exceptions import ConflictError, NotFoundError, ValidationError
from src.interfaces.document_service import IDocumentService
from src.interfaces.upload_session_service import IUploadSessionService
from src.models.category import Category
from src.models.upload_session import UploadSession
from src.services.document_service import get_document_service
from src.services.upload_strategies._shared import (
    DOCUMENT_EXTENSION_MAP,
    MAX_UPLOAD_SIZE,
    extract_ext,
    validate_mime_for_ext,
)

logger = logging.getLogger(__name__)


class UploadSessionService(IUploadSessionService):
    """Resumable uploads. The client owns the pacing: it opens a session, sends
    sequential chunks (pausing whenever it wants), asks `get_status` for the
    next offset to resume from, and calls `complete` once every byte arrived —
    only then the regular ingestion pipeline (extraction, embeddings) runs."""

    def __init__(self, session: Session, document_service: IDocumentService) -> None:
        self._session = session
        self._document_service = document_service

    @staticmethod
    def _serialize(row: UploadSession) -> dict:
        return {
            "id": row.id,
            "file_name": row.file_name,
            "category_id": row.category_id,
            "total_size": row.total_size,
            "bytes_received": row.bytes_received,
            "next_offset": row.bytes_received,
            "status": row.status,
        }

    def _load_owned(self, session_id: str, user_id: str) -> UploadSession:
        """Load a session or raise NotFoundError. Sessions from other users are
        reported as missing so ids can't be probed."""
        row = self._session.get(UploadSession, session_id)
        if row is None or row.user_id != user_id:
            raise NotFoundError(f"Upload session not found: {session_id}")
        return row

    def create_session(
        self,
        file_name: str,
        total_size: int,
        user_id: str,
        category_id: str | None = None,
    ) -> dict:
        name = file_name.strip()
        if not name:
            raise ValidationError("Missing file name.")
        ext = extract_ext(name)
        if ext not in DOCUMENT_EXTENSION_MAP:
            raise ValidationError(
                f"Unsupported file extension '{ext}'. "
                f"Accepted: {', '.join(sorted(DOCUMENT_EXTENSION_MAP))}."
            )
        if total_size <= 0:
            raise ValidationError("total_size must be a positive number of bytes.")
        if total_size > MAX_UPLOAD_SIZE:
            raise ValidationError(
                f"File exceeds {MAX_UPLOAD_SIZE // (1024 * 1024)}MB limit."
            )
        if category_id is not None and self._session.get(Category, category_id) is None:
            raise ValidationError(f"Unknown category: {category_id}")

        try:
            row = UploadSession(
                user_id=user_id,
                category_id=category_id,
                file_name=name,
                total_size=total_size,
                bytes_received=0,
                status=UploadSessionStatus.ACTIVE.value,
                data=b"",
            )
            self._session.add(row)
            self._session.commit()
            self._session.refresh(row)
        except Exception:
            self._session.rollback()
            raise
        return self._serialize(row)

    def get_status(self, session_id: str, user_id: str) -> dict:
        return self._serialize(self._load_owned(session_id, user_id))

    def append_chunk(
        self,
        session_id: str,
        user_id: str,
        offset: int,
        chunk: bytes,
    ) -> dict:
        row = self._load_owned(session_id, user_id)
        if row.status == UploadSessionStatus.COMPLETED.value:
            raise ConflictError("Upload session already completed.")
        if offset != row.bytes_received:
            raise ConflictError(
                f"Offset mismatch: got {offset}, session is at {row.bytes_received}. "
                f"Resume from {row.bytes_received}."
            )
        if row.bytes_received + len(chunk) > row.total_size:
            raise ValidationError(
                f"Chunk overflows the declared total size of {row.total_size} bytes."
            )
        try:
            row.data = row.data + chunk
            row.bytes_received += len(chunk)
            # Sending bytes to a paused session implicitly resumes it.
            row.status = UploadSessionStatus.ACTIVE.value
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._serialize(row)

    def pause(self, session_id: str, user_id: str) -> dict:
        row = self._load_owned(session_id, user_id)
        if row.status == UploadSessionStatus.COMPLETED.value:
            raise ConflictError("Upload session already completed.")
        try:
            row.status = UploadSessionStatus.PAUSED.value
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._serialize(row)

    def complete(self, session_id: str, user_id: str) -> dict:
        row = self._load_owned(session_id, user_id)
        if row.status == UploadSessionStatus.COMPLETED.value:
            raise ConflictError("Upload session already completed.")
        if row.bytes_received != row.total_size:
            raise ValidationError(
                f"Upload incomplete: {row.bytes_received}/{row.total_size} bytes "
                f"received. Send the remaining chunks before completing."
            )

        ext = extract_ext(row.file_name)
        content_type, category = DOCUMENT_EXTENSION_MAP[ext]
        validate_mime_for_ext(ext, row.data)

        result = self._document_service.upload_new_document(
            row.data,
            content_type,
            row.file_name,
            category,
            user_id,
            row.category_id,
        )
        # Mark done only after ingestion succeeded, so a failed pipeline leaves
        # the session resumable/retriable instead of losing the bytes.
        try:
            row.status = UploadSessionStatus.COMPLETED.value
            row.data = b""
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        logger.info(
            "upload session %s completed -> document=%s",
            session_id,
            result.get("document_id"),
        )
        return result

    def abort(self, session_id: str, user_id: str) -> None:
        row = self._load_owned(session_id, user_id)
        try:
            self._session.delete(row)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise


def get_upload_session_service(
    session: Session = Depends(get_session),
    document_service: IDocumentService = Depends(get_document_service),
) -> IUploadSessionService:
    return UploadSessionService(session, document_service)
