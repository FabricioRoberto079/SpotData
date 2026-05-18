from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from src.enums.content_type import ContentType
from src.enums.document_category import DocumentCategory, category_from_filename
from src.integrations.auth import get_current_user
from src.interfaces.document_service import IDocumentService
from src.interfaces.vector_index_service import IVectorIndexService
from src.models.user import User
from src.schemas.document import DocumentList, DocumentOut, SearchResults
from src.services.document_service import get_document_service
from src.services.vector_index_service import get_vector_index_service

MAX_UPLOAD_SIZE = 15 * 1024 * 1024


router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {
    ".pdf": ContentType.PDF,
    ".png": ContentType.FOTO,
    ".jpg": ContentType.FOTO,
    ".jpeg": ContentType.FOTO,
    ".txt": ContentType.TEXTO,
    ".md": ContentType.TEXTO,
    ".doc": ContentType.DOC,
    ".docx": ContentType.DOC,
}

_CONTENT_TYPE_TO_MIME = {
    ContentType.PDF.value: "application/pdf",
    ContentType.TEXTO.value: "text/plain; charset=utf-8",
    ContentType.FOTO.value: "application/octet-stream",
    ContentType.DOC.value: "application/octet-stream",
}


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_UPLOAD_SIZE // (1024 * 1024)}MB limit.",
        )
    return data


def _detect_content_type(filename: str) -> ContentType:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_type = ALLOWED_EXTENSIONS.get(ext)
    if content_type is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported extension: '{ext}'. "
            f"Accepted extensions: {', '.join(ALLOWED_EXTENSIONS.keys())}",
        )
    return content_type


def _upload_message(result: dict) -> str:
    version_number = result["version"]["version_number"]
    if result.get("created"):
        return f"Document created with version {version_number}."
    return f"Document already existed; version {version_number} added."


def _file_response(
    file_data: bytes, content_type: str, file_name: str, version_number: int
) -> Response:
    return Response(
        content=file_data,
        media_type=_CONTENT_TYPE_TO_MIME.get(content_type, "application/octet-stream"),
        headers={
            "Content-Disposition": f'inline; filename="{file_name}"',
            "X-Document-Version": str(version_number),
        },
    )


@router.get("", response_model=DocumentList, summary="List documents (paginated)")
async def list_all_documents(
    category: DocumentCategory | None = Query(
        default=None,
        description="Optional. Filter by category (documents/images/text). Omit to list all.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    return document_service.list_documents(category, limit=limit, offset=offset)


@router.post("/upload", summary="Create document from file (PDF, image, text)")
async def upload_document(
    file: UploadFile = File(...),
    file_name: str | None = Form(default=None),
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    filename = file.filename or ""
    content_type = _detect_content_type(filename)
    category = category_from_filename(filename)
    if category is None:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot derive category from filename: '{filename}'.",
        )
    file_data = await _read_upload(file)
    name = _clean_optional(file_name) or filename or "document"
    uploaded_by = current_user.id if current_user else None

    result = document_service.upload_new_document(
        file_data, content_type, name, category, uploaded_by
    )
    return {"message": _upload_message(result), **result}


@router.post("/text", summary="Create document from plain text")
async def ingest_text(
    text: str = Form(...),
    file_name: str = Form(default="plain-text"),
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text.")

    encoded = text.encode("utf-8")
    if len(encoded) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Text exceeds {MAX_UPLOAD_SIZE // (1024 * 1024)}MB limit.",
        )

    uploaded_by = current_user.id if current_user else None
    result = document_service.upload_new_document(
        encoded, ContentType.TEXTO, file_name, DocumentCategory.TEXT, uploaded_by
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
    current_user: User | None = Depends(get_current_user),
    vector_index: IVectorIndexService = Depends(get_vector_index_service),
):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Empty query.")
    return {"query": q, "results": vector_index.search(q, n_results=n_results)}


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document_metadata(
    document_id: str,
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    return document_service.get_document(document_id)


@router.delete("/{document_id}")
async def delete_document_endpoint(
    document_id: str,
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    document_service.delete_document(document_id)
    return {"message": "Document removed."}


@router.get("/{document_id}/download")
async def download_latest(
    document_id: str,
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    return _file_response(
        *document_service.get_version_file(document_id, version_number=None)
    )


@router.get("/{document_id}/versions/{version_number}/download")
async def download_version(
    document_id: str,
    version_number: int,
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    return _file_response(
        *document_service.get_version_file(document_id, version_number=version_number)
    )
