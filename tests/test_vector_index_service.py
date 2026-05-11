import pytest

from src.exceptions import ValidationError
from src.services.text_chunker import TextChunker
from src.services.vector_index_service import VectorIndexService


def test_index_text_pushes_chunks_to_collection(session, fake_collection, fake_llm):
    svc = VectorIndexService(session, TextChunker(max_chars=20, overlap=5), fake_llm)
    chunk_count = svc.index_text(
        document_id="doc-1",
        version_number=1,
        file_name="x.txt",
        content_type="texto",
        text="Frase um. Frase dois. Frase tres. Frase quatro.",
    )
    assert chunk_count >= 1
    assert len(fake_collection.upserts) == 1
    upsert = fake_collection.upserts[0]
    assert all(m["is_latest"] for m in upsert["metadatas"])
    assert all(m["document_id"] == "doc-1" for m in upsert["metadatas"])


def test_empty_text_raises_validation(session, fake_collection, fake_llm):
    svc = VectorIndexService(session, TextChunker(), fake_llm)
    with pytest.raises(ValidationError):
        svc.index_text("doc-1", 1, "x.txt", "texto", "")


def test_demote_latest_calls_chroma(session, fake_collection, fake_llm):
    svc = VectorIndexService(session, TextChunker(), fake_llm)
    svc.demote_latest("doc-1")
    assert fake_collection.deletes == [
        {"$and": [{"document_id": "doc-1"}, {"is_latest": True}]}
    ]


def test_purge_document_calls_chroma(session, fake_collection, fake_llm):
    svc = VectorIndexService(session, TextChunker(), fake_llm)
    svc.purge_document("doc-1")
    assert fake_collection.deletes == [{"document_id": "doc-1"}]


def test_search_empty_query_returns_empty(session, fake_collection, fake_llm):
    svc = VectorIndexService(session, TextChunker(), fake_llm)
    assert svc.search("") == []
    assert svc.search("   ") == []
