import logging
import re

from fastapi import Depends
from sqlalchemy import delete, func, literal_column, select, update
from sqlalchemy.orm import Session

from src.data.postgres_client import get_session
from src.exceptions import ValidationError
from src.integrations.llm import LlmClient, LlmError, get_llm_client
from src.interfaces.text_chunker import ITextChunker
from src.interfaces.vector_index_service import IVectorIndexService
from src.models.document_version import DocumentVersion
from src.models.knowledge_document import KnowledgeDocument
from src.models.vector_chunk import VectorChunk
from src.services.text_chunker import get_text_chunker

logger = logging.getLogger(__name__)

UPSERT_BATCH_SIZE = 100
HYBRID_CANDIDATE_K = 60
RRF_K = 60
TS_LANGUAGE = "portuguese"


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

    def prepare(self, text: str) -> tuple[list[str], list[list[float]]]:
        chunks = self._text_chunker.chunk(text)
        if not chunks:
            raise ValidationError("No usable text after chunking.")

        embeddings = self._llm.embed(chunks)
        if len(embeddings) != len(chunks):
            raise LlmError(
                "empty",
                502,
                f"Wrong embedding count (expected {len(chunks)}, got {len(embeddings)}).",
            )
        return chunks, embeddings

    def prepare_paged(
        self, pages: list[str]
    ) -> tuple[list[str], list[list[float]], list[int]]:
        chunks: list[str] = []
        pages_per_chunk: list[int] = []
        for page_no, page_text in enumerate(pages, start=1):
            if not page_text or not page_text.strip():
                continue
            page_chunks = self._text_chunker.chunk(page_text)
            chunks.extend(page_chunks)
            pages_per_chunk.extend([page_no] * len(page_chunks))

        if not chunks:
            raise ValidationError("No usable text after chunking.")

        embeddings = self._llm.embed(chunks)
        if len(embeddings) != len(chunks):
            raise LlmError(
                "empty",
                502,
                f"Wrong embedding count (expected {len(chunks)}, got {len(embeddings)}).",
            )
        return chunks, embeddings, pages_per_chunk

    def commit(
        self,
        document_id: str,
        version_number: int,
        file_name: str,
        content_type: str,
        chunks: list[str],
        embeddings: list[list[float]],
        pages_per_chunk: list[int | None] | None = None,
    ) -> int:
        self._session.execute(
            delete(VectorChunk).where(
                VectorChunk.document_id == document_id,
                VectorChunk.version_number == version_number,
            )
        )

        rows: list[VectorChunk] = []
        for i, chunk_text in enumerate(chunks):
            page: int | None = None
            if pages_per_chunk is not None and i < len(pages_per_chunk):
                page = pages_per_chunk[i]
            rows.append(
                VectorChunk(
                    document_id=document_id,
                    version_number=version_number,
                    chunk_index=i,
                    is_latest=True,
                    file_name=file_name,
                    content_type=content_type,
                    page=page,
                    snippet=chunk_text,
                    embedding=embeddings[i],
                )
            )

        for start in range(0, len(rows), UPSERT_BATCH_SIZE):
            self._session.add_all(rows[start : start + UPSERT_BATCH_SIZE])
            self._session.flush()
        return len(rows)

    def demote_latest(self, document_id: str) -> None:
        self._session.execute(
            update(VectorChunk)
            .where(
                VectorChunk.document_id == document_id,
                VectorChunk.is_latest.is_(True),
            )
            .values(is_latest=False)
        )

    def purge_document(self, document_id: str) -> None:
        self._session.execute(
            delete(VectorChunk).where(VectorChunk.document_id == document_id)
        )

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

        dialect = self._session.bind.dialect.name if self._session.bind else ""
        if dialect == "postgresql":
            return self._search_hybrid(query, n_results, embedding)
        return self._search_semantic(n_results, embedding)

    def _search_semantic(self, n_results: int, embedding: list[float]) -> list[dict]:
        distance = VectorChunk.embedding.cosine_distance(embedding)
        rows = self._session.execute(
            self._search_select(distance).order_by(distance.asc()).limit(n_results)
        ).all()
        return [self._row_to_dict(chunk, float(dist), doc_name, created_at)
                for chunk, dist, doc_name, created_at in rows]

    def _search_hybrid(
        self, query: str, n_results: int, embedding: list[float]
    ) -> list[dict]:
        distance = VectorChunk.embedding.cosine_distance(embedding)
        semantic_rows = self._session.execute(
            select(VectorChunk.id, distance.label("distance"))
            .where(VectorChunk.is_latest.is_(True))
            .order_by(distance.asc())
            .limit(HYBRID_CANDIDATE_K)
        ).all()

        bm25_rows: list = []
        tsquery_expr = self._build_or_tsquery(query)
        if tsquery_expr is not None:
            tsv = literal_column("tsv")
            tsquery = func.to_tsquery(TS_LANGUAGE, tsquery_expr)
            rank = func.ts_rank_cd(tsv, tsquery)
            bm25_rows = self._session.execute(
                select(VectorChunk.id, rank.label("rank"))
                .where(VectorChunk.is_latest.is_(True))
                .where(tsv.op("@@")(tsquery))
                .order_by(rank.desc())
                .limit(HYBRID_CANDIDATE_K)
            ).all()

        semantic_ranks = {row.id: i for i, row in enumerate(semantic_rows)}
        semantic_distances = {row.id: float(row.distance) for row in semantic_rows}
        bm25_ranks = {row.id: i for i, row in enumerate(bm25_rows)}

        rrf_scores: dict[str, float] = {}
        for chunk_id, r in semantic_ranks.items():
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + r + 1)
        for chunk_id, r in bm25_ranks.items():
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + r + 1)

        if not rrf_scores:
            return []

        top_ids = sorted(rrf_scores, key=lambda i: -rrf_scores[i])[:n_results]

        rows = self._session.execute(
            self._search_select().where(VectorChunk.id.in_(top_ids))
        ).all()
        by_id = {chunk.id: (chunk, doc_name, created_at)
                 for chunk, doc_name, created_at in rows}

        return [
            self._row_to_dict(
                chunk,
                semantic_distances.get(chunk_id, 1.0),
                doc_name,
                created_at,
            )
            for chunk_id in top_ids
            if chunk_id in by_id
            for chunk, doc_name, created_at in [by_id[chunk_id]]
        ]

    @staticmethod
    def _build_or_tsquery(query: str) -> str | None:
        tokens = [t for t in re.findall(r"\w+", query, flags=re.UNICODE) if len(t) > 1]
        if not tokens:
            return None
        return " | ".join(tokens)

    @staticmethod
    def _search_select(*extra_columns):
        return (
            select(
                VectorChunk,
                *extra_columns,
                KnowledgeDocument.file_name.label("doc_file_name"),
                DocumentVersion.created_at.label("version_created_at"),
            )
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == VectorChunk.document_id,
                isouter=True,
            )
            .join(
                DocumentVersion,
                (DocumentVersion.document_id == VectorChunk.document_id)
                & (DocumentVersion.version_number == VectorChunk.version_number),
                isouter=True,
            )
            .where(VectorChunk.is_latest.is_(True))
        )

    @staticmethod
    def _row_to_dict(chunk, distance, doc_file_name, version_created_at):
        return {
            "document_id": chunk.document_id,
            "version_number": chunk.version_number,
            "chunk_index": chunk.chunk_index,
            "file_name": doc_file_name or chunk.file_name,
            "content_type": chunk.content_type,
            "page": chunk.page,
            "distance": distance,
            "snippet": chunk.snippet,
            "version_created_at": version_created_at,
        }


def get_vector_index_service(
    session: Session = Depends(get_session),
    text_chunker: ITextChunker = Depends(get_text_chunker),
    llm: LlmClient = Depends(get_llm_client),
) -> IVectorIndexService:
    return VectorIndexService(session, text_chunker, llm)
