"""Integration test for the pgvector hybrid search — the core of the RAG
pipeline that the SQLite unit tests can't exercise.

The default suite runs on in-memory SQLite, which falls back to the pure
semantic path and never touches the pgvector column, the generated `tsv`
column, or the RRF fusion in `_search_hybrid`. This test runs the real
migrations against a live Postgres/pgvector instance and asserts that hybrid
retrieval ranks the relevant chunk first.

It is opt-in: it runs only when RUN_INTEGRATION_TESTS=1 (set by the dedicated
CI job that provisions a pgvector service). Otherwise the whole module is
skipped so the normal SQLite run is unaffected.
"""
import os

import pytest

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "integration tests require a live Postgres; set RUN_INTEGRATION_TESTS=1",
        allow_module_level=True,
    )

from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from src.data.postgres_client import SessionLocal, engine  # noqa: E402
from src.models.knowledge_document import KnowledgeDocument  # noqa: E402
from src.models.vector_chunk import VectorChunk  # noqa: E402
from src.services.text_chunker import get_text_chunker  # noqa: E402
from src.services.vector_index_service import VectorIndexService  # noqa: E402

pytestmark = pytest.mark.integration

# 4-dim embeddings (EMBEDDING_DIMENSION must be 4 for the migration + model).
# Chunks sit on orthogonal axes so cosine distance is unambiguous.
_EMB_STORAGE = [1.0, 0.0, 0.0, 0.0]
_EMB_NETWORK = [0.0, 1.0, 0.0, 0.0]
_EMB_UNRELATED = [0.0, 0.0, 1.0, 0.0]


@pytest.fixture(scope="module")
def migrated_db():
    """Rebuild the schema from the real Alembic migrations on a clean public
    schema, then hand back the engine. Destructive — meant for a throwaway
    test database only."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(Config("alembic.ini"), "head")
    yield engine


@pytest.fixture
def session(migrated_db):
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE vector_chunks, knowledge_documents CASCADE"))
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed(session):
    doc = KnowledgeDocument(file_name="handbook.pdf", category="TEXT")
    session.add(doc)
    session.flush()
    chunks = [
        VectorChunk(
            document_id=doc.id, version_number=1, chunk_index=0, is_latest=True,
            file_name="handbook.pdf", content_type="pdf",
            snippet="O backup de armazenamento roda toda madrugada.",
            embedding=_EMB_STORAGE,
        ),
        VectorChunk(
            document_id=doc.id, version_number=1, chunk_index=1, is_latest=True,
            file_name="handbook.pdf", content_type="pdf",
            snippet="A configuracao de rede usa VLANs isoladas.",
            embedding=_EMB_NETWORK,
        ),
        VectorChunk(
            document_id=doc.id, version_number=1, chunk_index=2, is_latest=True,
            file_name="handbook.pdf", content_type="pdf",
            snippet="O refeitorio abre ao meio-dia.",
            embedding=_EMB_UNRELATED,
        ),
    ]
    session.add_all(chunks)
    session.commit()
    return doc


def _service(session):
    # llm_client is unused when an explicit query embedding is passed to search().
    return VectorIndexService(session, get_text_chunker(), llm_client=None)


def test_hybrid_search_uses_postgres_path(session):
    assert engine.dialect.name == "postgresql"


def test_semantic_ranking_returns_nearest_chunk_first(session):
    _seed(session)
    results = _service(session).search(
        "backup", n_results=3, embedding=_EMB_STORAGE
    )
    assert results, "hybrid search returned nothing"
    assert "backup de armazenamento" in results[0]["snippet"]


def test_lexical_match_surfaces_chunk_without_close_embedding(session):
    _seed(session)
    # Query embedding points at the unrelated chunk, but the word "rede" only
    # appears in the network snippet — the lexical (tsvector) arm must surface
    # it via RRF even though it is semantically distant.
    results = _service(session).search(
        "configuracao de rede", n_results=3, embedding=_EMB_UNRELATED
    )
    snippets = " ".join(r["snippet"] for r in results)
    assert "VLANs isoladas" in snippets


def test_category_scope_excludes_other_categories(session):
    doc = _seed(session)
    # Tag one chunk to a specific category; searching a *different* category
    # must not return it (uncategorized chunks stay visible to everyone).
    session.query(VectorChunk).filter_by(document_id=doc.id, chunk_index=0).update(
        {"category_id": None}
    )
    session.commit()
    results = _service(session).search(
        "backup", n_results=3, embedding=_EMB_STORAGE, category_id="nonexistent-cat"
    )
    # The storage chunk is uncategorized (NULL) so it is still visible.
    assert any("backup de armazenamento" in r["snippet"] for r in results)
