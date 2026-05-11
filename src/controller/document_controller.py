from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from src.enums.content_type import ContentType
from src.integrations.auth import get_current_user
from src.interfaces.document_service import IDocumentService
from src.interfaces.vector_index_service import IVectorIndexService
from src.models.user import User
from src.schemas.document import (
    DocumentList,
    DocumentOut,
    DocumentVersionOut,
    SearchResults,
)
from src.services.document_service import get_document_service
from src.services.vector_index_service import get_vector_index_service


class DocumentUpdate(BaseModel):
    file_name: str | None = None
    folder_id: str | None = None
    clear_folder: bool = False


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


@router.get("", response_model=DocumentList, summary="List documents (paginated)")
async def list_all_documents(
    folder_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    return document_service.list_documents(folder_id, limit=limit, offset=offset)


@router.post("/upload", summary="Create document from file (PDF, image, text)")
async def upload_document(
    file: UploadFile = File(...),
    file_name: str | None = Form(default=None),
    folder_id: str | None = Form(default=None),
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    content_type = _detect_content_type(file.filename or "")
    file_data = await file.read()

    if not file_data:
        raise HTTPException(status_code=400, detail="Empty file.")

    name = file_name or file.filename or "document"
    uploaded_by = current_user.id if current_user else None

    result = document_service.upload_new_document(
        file_data, content_type, name, folder_id, uploaded_by
    )
    return {"message": "Document created with version 1.", **result}


@router.post("/text", summary="Create document from plain text")
async def ingest_text(
    text: str = Form(...),
    file_name: str = Form(default="plain-text"),
    folder_id: str | None = Form(default=None),
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text.")

    uploaded_by = current_user.id if current_user else None
    result = document_service.upload_new_document(
        text.encode("utf-8"),
        ContentType.TEXTO,
        file_name,
        folder_id,
        uploaded_by,
    )
    return {"message": "Document created with version 1.", **result}


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


@router.patch("/{document_id}", response_model=DocumentOut)
async def patch_document(
    document_id: str,
    payload: DocumentUpdate,
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    return document_service.update_document(
        document_id,
        file_name=payload.file_name,
        folder_id=payload.folder_id,
        clear_folder=payload.clear_folder,
    )


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
    file_data, content_type, file_name, version_number = (
        document_service.get_version_file(document_id, version_number=None)
    )
    return Response(
        content=file_data,
        media_type=_CONTENT_TYPE_TO_MIME.get(content_type, "application/octet-stream"),
        headers={
            "Content-Disposition": f'inline; filename="{file_name}"',
            "X-Document-Version": str(version_number),
        },
    )


@router.post("/{document_id}/versions")
async def create_new_version(
    document_id: str,
    file: UploadFile = File(...),
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    content_type = _detect_content_type(file.filename or "")
    file_data = await file.read()

    if not file_data:
        raise HTTPException(status_code=400, detail="Empty file.")

    version = document_service.add_version(document_id, file_data, content_type)
    return {"message": f"Version {version['version_number']} created.", **version}


@router.get("/{document_id}/versions")
async def get_versions(
    document_id: str,
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
) -> dict:
    versions = document_service.list_versions(document_id)
    return {
        "document_id": document_id,
        "versions": [DocumentVersionOut(**v).model_dump() for v in versions],
    }


@router.get("/{document_id}/versions/{version_number}/download")
async def download_version(
    document_id: str,
    version_number: int,
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    file_data, content_type, file_name, version_number = (
        document_service.get_version_file(document_id, version_number=version_number)
    )
    return Response(
        content=file_data,
        media_type=_CONTENT_TYPE_TO_MIME.get(content_type, "application/octet-stream"),
        headers={
            "Content-Disposition": f'inline; filename="{file_name}"',
            "X-Document-Version": str(version_number),
        },
    )


@router.post("/{document_id}/versions/{version_number}/retry")
async def retry_version_indexing(
    document_id: str,
    version_number: int,
    current_user: User | None = Depends(get_current_user),
    document_service: IDocumentService = Depends(get_document_service),
):
    return document_service.retry_vectorization(document_id, version_number)
