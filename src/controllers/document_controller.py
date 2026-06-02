import asyncio
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response

from src.enums.content_type import ContentType
from src.enums.upload_kind import UploadKind
from src.enums.user_role import UserRole
from src.exceptions import ValidationError
from src.auth import require_role
from src.interfaces.document_service import IDocumentService
from src.interfaces.vector_index_service import IVectorIndexService
from src.models.user import User
from src.schemas.document import DocumentList, DocumentOut, SearchResults
from src.services.access import get_allowed_category_ids
from src.services.document_service import get_document_service
from src.services.upload_strategies import get_upload_strategy
from src.services.vector_index_service import get_vector_index_service

router = APIRouter(prefix="/documents", tags=["documents"])

_CONTENT_TYPE_TO_MIME = {
    ContentType.PDF.value: "application/pdf",
    ContentType.TEXTO.value: "text/plain; charset=utf-8",
    ContentType.FOTO.value: "application/octet-stream",
    ContentType.DOC.value: "application/octet-stream",
}


def _upload_message(result: dict) -> str:
    version_number = result["version"]["version_number"]
    if result.get("created"):
        return f"Document created with version {version_number}."
    return f"Document already existed; version {version_number} added."


def _content_disposition(file_name: str) -> str:
    """RFC 5987 / 6266 quoting: prevents CRLF / quote injection in filename."""
    ascii_fallback = file_name.encode("ascii", "replace").decode("ascii").replace('"', "")
    encoded = quote(file_name, safe="")
    return f'inline; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def _file_response(
    file_data: bytes, content_type: str, file_name: str, version_number: int
) -> Response:
    return Response(
        content=file_data,
        media_type=_CONTENT_TYPE_TO_MIME.get(content_type, "application/octet-stream"),
        headers={
            "Content-Disposition": _content_disposition(file_name),
            "X-Document-Version": str(version_number),
        },
    )


@router.get("", response_model=DocumentList, summary="List documents (paginated)")
async def list_all_documents(
    category_id: str | None = Query(
        default=None,
        description="Optional. Filter by category id. Omit to list everything you can access.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    allowed_category_ids: list[str] | None = Depends(get_allowed_category_ids),
    document_service: IDocumentService = Depends(get_document_service),
):
    return document_service.list_documents(
        category_id,
        limit=limit,
        offset=offset,
        allowed_category_ids=allowed_category_ids,
    )


@router.post(
    "/upload",
    summary="Upload a document (file, image, or plain text)",
    description=(
        "Single entry point for ingestion. Pick a `kind`:\n"
        "- `file` → send `file` (PDF, DOC, DOCX, TXT, MD).\n"
        "- `image` → send `file` (PNG, JPG, JPEG).\n"
        "- `text` → send `text` (plain text body).\n\n"
        "Requires a `category_id` you have access to. "
        "Optional `file_name` overrides the stored name. Viewers cannot upload."
    ),
)
async def upload_document(
    kind: UploadKind = Form(..., description="Strategy: 'file', 'image' or 'text'."),
    category_id: str = Form(
        ..., description="Target category id. Must be one you are linked to."
    ),
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    file_name: str | None = Form(default=None),
    current_user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN)),
    allowed_category_ids: list[str] | None = Depends(get_allowed_category_ids),
    document_service: IDocumentService = Depends(get_document_service),
):
    try:
        strategy = get_upload_strategy(kind)
    except KeyError:
        raise ValidationError(f"Unknown upload kind: '{kind}'.")

    payload = await strategy.build_payload(file=file, text=text, file_name=file_name)

    # Heavy CPU work (extraction, embeddings, vector upsert) — keep the event loop free.
    result = await asyncio.to_thread(
        document_service.upload_new_document,
        payload.file_data,
        payload.content_type,
        payload.file_name,
        payload.category,
        current_user.id,
        category_id,
        allowed_category_ids,
    )
    return {"message": _upload_message(result), **result}


@router.get(
    "/search",
    response_model=SearchResults,
    summary="Semantic search over latest chunks",
)
async def search_documents(
    q: str,
    n_results: int = Query(default=5, ge=1, le=20),
    allowed_category_ids: list[str] | None = Depends(get_allowed_category_ids),
    vector_index: IVectorIndexService = Depends(get_vector_index_service),
):
    if not q.strip():
        raise ValidationError("Empty query.")
    results = await asyncio.to_thread(
        vector_index.search, q, n_results, None, allowed_category_ids
    )
    return {"query": q, "results": results}


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document_metadata(
    document_id: str,
    allowed_category_ids: list[str] | None = Depends(get_allowed_category_ids),
    document_service: IDocumentService = Depends(get_document_service),
):
    return document_service.get_document(
        document_id, allowed_category_ids=allowed_category_ids
    )


@router.delete("/{document_id}")
async def delete_document_endpoint(
    document_id: str,
    allowed_category_ids: list[str] | None = Depends(get_allowed_category_ids),
    document_service: IDocumentService = Depends(get_document_service),
):
    document_service.delete_document(
        document_id, allowed_category_ids=allowed_category_ids
    )
    return {"message": "Document removed."}


@router.get("/{document_id}/download")
async def download_latest(
    document_id: str,
    allowed_category_ids: list[str] | None = Depends(get_allowed_category_ids),
    document_service: IDocumentService = Depends(get_document_service),
):
    return _file_response(
        *document_service.get_version_file(
            document_id,
            version_number=None,
            allowed_category_ids=allowed_category_ids,
        )
    )


@router.get("/{document_id}/versions/{version_number}/download")
async def download_version(
    document_id: str,
    version_number: int,
    allowed_category_ids: list[str] | None = Depends(get_allowed_category_ids),
    document_service: IDocumentService = Depends(get_document_service),
):
    return _file_response(
        *document_service.get_version_file(
            document_id,
            version_number=version_number,
            allowed_category_ids=allowed_category_ids,
        )
    )
