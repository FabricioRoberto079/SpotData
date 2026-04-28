from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from src.Enums.content_type import ContentType
from src.Services.vector_service import insert_from_bytes, search

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {
    ".pdf": ContentType.PDF,
    ".png": ContentType.FOTO,
    ".jpg": ContentType.FOTO,
    ".jpeg": ContentType.FOTO,
    ".bmp": ContentType.FOTO,
    ".tiff": ContentType.FOTO,
    ".txt": ContentType.TEXTO,
}


def _detect_content_type(filename: str) -> ContentType:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_type = ALLOWED_EXTENSIONS.get(ext)
    if content_type is None:
        raise HTTPException(
            status_code=400,
            detail=f"Extensao nao suportada: '{ext}'. "
            f"Extensoes aceitas: {', '.join(ALLOWED_EXTENSIONS.keys())}",
        )
    return content_type


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    source_name: str | None = Form(default=None),
):
    """
    Recebe um arquivo (PDF, imagem ou texto) via upload.
    Extrai o texto, salva no Postgres e no ChromaDB.
    """
    content_type = _detect_content_type(file.filename or "")
    file_data = await file.read()

    if not file_data:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    name = source_name or file.filename or "documento"

    try:
        doc_id = insert_from_bytes(file_data, content_type, name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "id": doc_id,
        "source_name": name,
        "content_type": content_type.value,
        "message": "Documento processado e salvo com sucesso.",
    }


@router.post("/text")
async def ingest_text(
    text: str = Form(...),
    source_name: str = Form(default="texto-direto"),
):
    """
    Recebe texto puro diretamente (sem arquivo).
    Salva no Postgres e no ChromaDB.
    """
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Texto vazio.")

    file_data = text.encode("utf-8")

    try:
        doc_id = insert_from_bytes(file_data, ContentType.TEXTO, source_name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "id": doc_id,
        "source_name": source_name,
        "content_type": ContentType.TEXTO.value,
        "message": "Texto processado e salvo com sucesso.",
    }


@router.get("/search")
async def search_documents(q: str, n_results: int = 3):
    """
    Busca semantica nos documentos indexados.
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query vazia.")

    results = search(q, n_results=n_results)
    return {"query": q, "results": results}
