import os

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("EMBEDDING_DIMENSION", "4")

from src.integrations.llm import LlmClient
from src.interfaces.qa_cache import IQaCache, question_key
from src.interfaces.vector_index_service import IVectorIndexService
from src.models.base_model import Base


def make_structured_partials(
    answer: str = "",
    citations: list[dict] | None = None,
) -> list[dict]:
    """Emulate the partial dict snapshots that `JsonOutputParser` yields from a
    `RagAnswer` JSON stream. The schema lists `citations` before `answer`, so:

    1. Citations array grows entry by entry (no `answer` key yet).
    2. Once the array closes, the `answer` key appears and grows in 2-word chunks.
    """
    cits = list(citations or [])
    partials: list[dict] = []

    for i in range(1, len(cits) + 1):
        partials.append({"citations": cits[:i]})

    if answer:
        words = answer.split(" ")
        current = ""
        for w in words:
            current = f"{current} {w}".strip() if current else w
            partials.append({"citations": cits, "answer": current})
    else:
        partials.append({"citations": cits, "answer": ""})

    return partials


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")

    # SQLite disables FK enforcement by default; enable it so cascade gaps
    # surface in tests instead of silently passing.
    @event.listens_for(eng, "connect")
    def _enable_sqlite_fk(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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
    def __init__(
        self,
        structured_partials: list[dict] | None = None,
        stream_error: Exception | None = None,
    ) -> None:
        self.structured_partials = structured_partials
        self.stream_error = stream_error
        self.embed_calls: list[list[str]] = []

    async def chat_stream_structured(
        self, messages, schema, model=None, temperature=0.0, max_tokens=None
    ):
        if self.stream_error is not None:
            raise self.stream_error
        for partial in self.structured_partials or []:
            yield partial

    def embed(self, texts, model=None):
        self.embed_calls.append(list(texts))
        return [[0.0] * 4 for _ in texts]


@pytest.fixture
def fake_llm():
    return FakeLlm()


class StubVectorIndex(IVectorIndexService):
    def __init__(self, results=None) -> None:
        self._results = results or []
        self.last_commit: dict | None = None

    def prepare(self, text):
        return ([text], [[0.0] * 4])

    def prepare_paged(self, pages):
        chunks: list[str] = []
        pages_per_chunk: list[int] = []
        for i, page in enumerate(pages, start=1):
            if not page or not page.strip():
                continue
            chunks.append(page)
            pages_per_chunk.append(i)
        embeddings = [[0.0] * 4 for _ in chunks]
        return chunks, embeddings, pages_per_chunk

    def commit(
        self,
        document_id,
        version_number,
        file_name,
        content_type,
        chunks,
        embeddings,
        pages_per_chunk=None,
        category_id=None,
    ):
        self.last_commit = {
            "document_id": document_id,
            "version_number": version_number,
            "chunks": list(chunks),
            "pages_per_chunk": list(pages_per_chunk) if pages_per_chunk else None,
            "category_id": category_id,
        }
        return len(chunks)

    def demote_latest(self, document_id):
        pass

    def purge_document(self, document_id):
        pass

    def search(self, query, n_results=5, embedding=None, category_id=None):
        self.last_search_scope = category_id
        return self._results


class StubQaCache(IQaCache):
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self.semantic_hits: dict[str, dict] = {}
        self.invalidate_calls = 0

    def lookup_exact(self, question):
        return self.store.get(question_key(question))

    def lookup_semantic(self, question, embedding):
        return self.semantic_hits.get(question_key(question))

    def put(self, question, embedding, payload):
        self.store[question_key(question)] = payload

    def invalidate_all(self):
        self.invalidate_calls += 1
        self.store.clear()
        self.semantic_hits.clear()

    def stats(self):
        return {"size": len(self.store), "invalidations": self.invalidate_calls}
