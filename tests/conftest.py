import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET", "test-secret")

from src.integrations.llm import LlmClient
from src.interfaces.vector_index_service import IVectorIndexService
from src.models.base_model import Base


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        Base.metadata.drop_all(eng)


@pytest.fixture
def session(engine):
    SessionMaker = sessionmaker(bind=engine)
    s = SessionMaker()
    try:
        yield s
    finally:
        s.close()


class FakeLlm(LlmClient):
    def __init__(self, structured_response=None) -> None:
        self.structured_response = structured_response
        self.embed_calls: list[list[str]] = []

    def chat(self, messages, model=None, temperature=0.2, max_tokens=None):
        return "fake answer"

    def chat_structured(
        self, messages, response_model, model=None, temperature=0.0, max_tokens=None
    ):
        if self.structured_response is None:
            raise RuntimeError("FakeLlm.structured_response not configured")
        return self.structured_response

    def embed(self, texts, model=None):
        self.embed_calls.append(list(texts))
        return [[0.0] * 4 for _ in texts]


class FakeCollection:
    def __init__(self):
        self.upserts: list[dict] = []
        self.deletes: list[dict] = []
        self.query_response = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

    def upsert(self, ids, documents, embeddings, metadatas):
        self.upserts.append(
            {"ids": ids, "documents": documents, "metadatas": metadatas}
        )

    def delete(self, where):
        self.deletes.append(where)

    def query(self, query_embeddings, n_results, where):
        return self.query_response


@pytest.fixture
def fake_collection(monkeypatch):
    coll = FakeCollection()

    def _fake_get_chroma_client():
        class _Client:
            def get_or_create_collection(self, name):
                return coll

        return _Client()

    monkeypatch.setattr(
        "src.services.vector_index_service.get_chroma_client",
        _fake_get_chroma_client,
    )
    return coll


@pytest.fixture
def fake_llm():
    return FakeLlm()


class StubVectorIndex(IVectorIndexService):
    def __init__(self, results=None) -> None:
        self._results = results or []

    def prepare(self, text):
        return ([text], [[0.0] * 4])

    def commit(self, document_id, version_number, file_name, content_type, chunks, embeddings):
        return len(chunks)

    def demote_latest(self, document_id):
        pass

    def purge_document(self, document_id):
        pass

    def search(self, query, n_results=5):
        return self._results
