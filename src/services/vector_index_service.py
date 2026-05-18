import logging

from fastapi import Depends
from sqlalchemy.orm import Session

from sqlalchemy import select

from src.data.chroma_client import get_chroma_client
from src.data.postgres_client import get_session
from src.exceptions import ValidationError
from src.integrations.llm import LlmClient, LlmError, get_llm_client
from src.interfaces.text_chunker import ITextChunker
from src.interfaces.vector_index_service import IVectorIndexService
from src.models.document_version import DocumentVersion
from src.models.knowledge_document import KnowledgeDocument
from src.services.text_chunker import get_text_chunker

logger = logging.getLogger(__name__)

COLLECTION_NAME = "spots"
UPSERT_BATCH_SIZE = 100


class VectorIndexService(IVectorIndexService):
    def __init__(
        self,
        session: Session,
        text_chunker: ITextChunker,
        llm_client: LlmClient,
    ) -> None:
        self._session = session
        self._text_chunker = text_chunker
        self._llm = llm_client

    def _get_collection(self):
        client = get_chroma_client()
        return client.get_or_create_collection(name=COLLECTION_NAME)

    @staticmethod
    def _chunk_id(document_id: str, version_number: int, chunk_index: int) -> str:
        return f"{document_id}:{version_number}:{chunk_index}"

    def prepare(self, text: str) -> tuple[list[str], list[list[float]]]:
        chunks = self._text_chunker.chunk(text)
        if not chunks:
            raise ValidationError("No usable text after chunking.")

        embeddings = self._llm.embed(chunks)
        if len(embeddings) != len(chunks):
            raise LlmError(
                "empty",
                502,
                f"Embeddings em quantidade incorreta (esperado {len(chunks)}, recebido {len(embeddings)}).",
            )
        return chunks, embeddings

    def commit(
        self,
        document_id: str,
        version_number: int,
        file_name: str,
        content_type: str,
        chunks: list[str],
        embeddings: list[list[float]],
    ) -> int:
        ids = [
            self._chunk_id(document_id, version_number, i) for i in range(len(chunks))
        ]
        metadatas = [
            {
                "document_id": document_id,
                "version_number": version_number,
                "is_latest": True,
                "content_type": content_type,
                "file_name": file_name,
                "chunk_index": i,
                "chunk_count": len(chunks),
            }
            for i in range(len(chunks))
        ]
        collection = self._get_collection()
        for start in range(0, len(chunks), UPSERT_BATCH_SIZE):
            end = start + UPSERT_BATCH_SIZE
            collection.upsert(
                ids=ids[start:end],
                documents=chunks[start:end],
                embeddings=embeddings[start:end],
                metadatas=metadatas[start:end],
            )
        return len(chunks)

    def demote_latest(self, document_id: str) -> None:
        self._get_collection().delete(
            where={"$and": [{"document_id": document_id}, {"is_latest": True}]}
        )

    def purge_document(self, document_id: str) -> None:
        self._get_collection().delete(where={"document_id": document_id})

    def search(
        self,
        query: str,
        n_results: int = 5,
        embedding: list[float] | None = None,
    ) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []

        if embedding is None:
            [embedding] = self._llm.embed([query])
        results = self._get_collection().query(
            query_embeddings=[embedding],
            n_results=n_results,
            where={"is_latest": True},
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        items = []
        for vec_id, doc_text, metadata, distance in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            document_id = metadata.get("document_id")
            version_number = metadata.get("version_number")
            doc = (
                self._session.get(KnowledgeDocument, document_id)
                if document_id
                else None
            )
            version = None
            if document_id and version_number is not None:
                version = self._session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == document_id,
                        DocumentVersion.version_number == version_number,
                    )
                ).scalar_one_or_none()
            items.append(
                {
                    "vector_id": vec_id,
                    "document_id": document_id,
                    "version_number": version_number,
                    "chunk_index": metadata.get("chunk_index"),
                    "file_name": doc.file_name if doc else metadata.get("file_name"),
                    "content_type": metadata.get("content_type"),
                    "distance": distance,
                    "snippet": doc_text,
                    "version_created_at": version.created_at if version else None,
                }
            )
        return items


def get_vector_index_service(
    session: Session = Depends(get_session),
    text_chunker: ITextChunker = Depends(get_text_chunker),
    llm: LlmClient = Depends(get_llm_client),
) -> IVectorIndexService:
    return VectorIndexService(session, text_chunker, llm)
