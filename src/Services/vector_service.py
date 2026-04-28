import uuid
from chromadb import Collection

from src.Data.chroma_client import get_chroma_client
from src.Data.postgres_client import SessionLocal
from src.Enums.content_type import ContentType
from src.Models.spot import Spot
from src.Services.text_extractor import extract_text, extract_text_from_bytes

COLLECTION_NAME = "spots"


def _get_collection() -> Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(name=COLLECTION_NAME)


def _save_to_stores(
    doc_id: str,
    source_name: str,
    content_type: ContentType,
    file_data: bytes,
    text: str,
) -> str:
    """Salva no Postgres e no ChromaDB."""
    session = SessionLocal()
    try:
        spot = Spot(
            id=doc_id,
            source_name=source_name,
            content_type=content_type,
            file_data=file_data,
            extracted_text=text,
        )
        session.add(spot)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    collection = _get_collection()
    collection.upsert(
        ids=[doc_id],
        documents=[text],
        metadatas=[{
            "content_type": content_type,
            "source": source_name,
        }],
    )

    return doc_id


def insert(file_path: str, content_type: ContentType, source_name: str | None = None) -> str:
    """
    Insere a partir de um arquivo no disco.
    1. Extrai texto do arquivo
    2. Salva arquivo original + texto no Postgres
    3. Salva texto + embedding no ChromaDB (mesmo ID)
    """
    text = extract_text(file_path, content_type)
    if not text:
        raise ValueError("Nenhum texto extraído do arquivo.")

    with open(file_path, "rb") as f:
        file_data = f.read()

    doc_id = str(uuid.uuid4())
    name = source_name or file_path

    return _save_to_stores(doc_id, name, content_type, file_data, text)


def insert_from_bytes(
    file_data: bytes,
    content_type: ContentType,
    source_name: str,
) -> str:
    """
    Insere a partir de bytes (upload via API).
    1. Extrai texto dos bytes
    2. Salva bytes originais + texto no Postgres
    3. Salva texto + embedding no ChromaDB (mesmo ID)
    """
    text = extract_text_from_bytes(file_data, content_type)
    if not text:
        raise ValueError("Nenhum texto extraído do conteúdo enviado.")

    doc_id = str(uuid.uuid4())

    return _save_to_stores(doc_id, source_name, content_type, file_data, text)


def search(query: str, n_results: int = 3) -> list[dict]:
    """
    1. Busca semântica no ChromaDB
    2. Busca o registro completo no Postgres pelo ID
    """
    collection = _get_collection()
    results = collection.query(query_texts=[query], n_results=n_results)

    if not results["ids"][0]:
        return []

    session = SessionLocal()
    try:
        items = []
        for doc_id, doc, metadata, distance in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            spot = session.get(Spot, doc_id)
            items.append({
                "id": doc_id,
                "document": doc,
                "metadata": metadata,
                "distance": distance,
                "source_name": spot.source_name if spot else None,
                "content_type": spot.content_type if spot else None,
            })
        return items
    finally:
        session.close()
