import pytest
from sqlalchemy import select

from src.enums.document_category import DocumentCategory
from src.exceptions import ValidationError
from src.models.category import Category
from src.models.knowledge_document import KnowledgeDocument
from src.models.vector_chunk import VectorChunk
from src.services.text_chunker import TextChunker
from src.services.vector_index_service import VectorIndexService


def _seed_document(session, doc_id: str = "doc-1") -> None:
    session.add(
        KnowledgeDocument(
            id=doc_id, file_name="x.txt", category=DocumentCategory.DOCUMENTS.value
        )
    )
    session.commit()


def test_prepare_chunks_and_embeds(session, fake_llm):
    svc = VectorIndexService(session, TextChunker(max_chars=20, overlap=5), fake_llm)
    chunks, embeddings = svc.prepare(
        "Frase um. Frase dois. Frase tres. Frase quatro."
    )
    assert len(chunks) >= 1
    assert len(embeddings) == len(chunks)


def test_prepare_empty_text_raises_validation(session, fake_llm):
    svc = VectorIndexService(session, TextChunker(), fake_llm)
    with pytest.raises(ValidationError):
        svc.prepare("")


def test_commit_persists_chunks_with_is_latest(session, fake_llm):
    _seed_document(session)
    svc = VectorIndexService(session, TextChunker(max_chars=20, overlap=5), fake_llm)
    chunks, embeddings = svc.prepare(
        "Frase um. Frase dois. Frase tres. Frase quatro."
    )
    count = svc.commit(
        document_id="doc-1",
        version_number=1,
        file_name="x.txt",
        content_type="texto",
        chunks=chunks,
        embeddings=embeddings,
    )
    rows = session.execute(select(VectorChunk)).scalars().all()
    assert count == len(rows) >= 1
    assert all(r.document_id == "doc-1" for r in rows)
    assert all(r.is_latest for r in rows)


def test_commit_is_idempotent_per_version(session, fake_llm):
    _seed_document(session)
    svc = VectorIndexService(session, TextChunker(max_chars=20, overlap=5), fake_llm)
    chunks, embeddings = svc.prepare("Frase um. Frase dois.")
    svc.commit(
        document_id="doc-1",
        version_number=1,
        file_name="x.txt",
        content_type="texto",
        chunks=chunks,
        embeddings=embeddings,
    )
    first_count = session.execute(select(VectorChunk)).scalars().all()
    svc.commit(
        document_id="doc-1",
        version_number=1,
        file_name="x.txt",
        content_type="texto",
        chunks=chunks,
        embeddings=embeddings,
    )
    second_count = session.execute(select(VectorChunk)).scalars().all()
    assert len(second_count) == len(first_count)


def test_demote_latest_flips_flag(session, fake_llm):
    _seed_document(session)
    svc = VectorIndexService(session, TextChunker(max_chars=20, overlap=5), fake_llm)
    chunks, embeddings = svc.prepare("Texto curto.")
    svc.commit(
        document_id="doc-1",
        version_number=1,
        file_name="x.txt",
        content_type="texto",
        chunks=chunks,
        embeddings=embeddings,
    )
    svc.demote_latest("doc-1")
    rows = session.execute(select(VectorChunk)).scalars().all()
    assert rows
    assert all(not r.is_latest for r in rows)


def test_purge_document_removes_all_chunks(session, fake_llm):
    _seed_document(session)
    svc = VectorIndexService(session, TextChunker(max_chars=20, overlap=5), fake_llm)
    chunks, embeddings = svc.prepare("Texto curto.")
    svc.commit(
        document_id="doc-1",
        version_number=1,
        file_name="x.txt",
        content_type="texto",
        chunks=chunks,
        embeddings=embeddings,
    )
    svc.purge_document("doc-1")
    rows = session.execute(select(VectorChunk)).scalars().all()
    assert rows == []


def test_search_empty_query_returns_empty(session, fake_llm):
    svc = VectorIndexService(session, TextChunker(), fake_llm)
    assert svc.search("") == []
    assert svc.search("   ") == []


def test_commit_persists_category_id(session, fake_llm):
    _seed_document(session)
    session.add(Category(id="cat-9", name="Nove", slug="nove"))
    session.commit()
    svc = VectorIndexService(session, TextChunker(max_chars=20, overlap=5), fake_llm)
    chunks, embeddings = svc.prepare("Frase um. Frase dois.")
    svc.commit(
        document_id="doc-1",
        version_number=1,
        file_name="x.txt",
        content_type="texto",
        chunks=chunks,
        embeddings=embeddings,
        category_id="cat-9",
    )
    rows = session.execute(select(VectorChunk)).scalars().all()
    assert rows
    assert all(r.category_id == "cat-9" for r in rows)
