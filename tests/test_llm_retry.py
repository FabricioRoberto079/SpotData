"""Retry behaviour of the embedding call.

Transient provider errors (rate limit / timeout) are retried with backoff;
deterministic errors (bad API key) fail fast without wasting attempts.
"""

import pytest

from src.integrations import llm
from src.integrations.llm import LlmClient, LlmError


class _FlakyEmbeddings:
    def __init__(self, fail_times: int, error_message: str):
        self.calls = 0
        self._fail_times = fail_times
        self._error_message = error_message

    def embed_documents(self, texts):
        self.calls += 1
        if self.calls <= self._fail_times:
            raise RuntimeError(self._error_message)
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)


def test_embed_retries_transient_error_then_succeeds(monkeypatch):
    stub = _FlakyEmbeddings(fail_times=2, error_message="rate limit exceeded (429)")
    monkeypatch.setattr(llm, "_get_embeddings", lambda _spec: stub)

    result = LlmClient().embed(["a", "b"], model="stub:model")

    assert stub.calls == 3
    assert result == [[0.1, 0.2, 0.3, 0.4], [0.1, 0.2, 0.3, 0.4]]


def test_embed_does_not_retry_auth_error(monkeypatch):
    stub = _FlakyEmbeddings(fail_times=5, error_message="invalid api key")
    monkeypatch.setattr(llm, "_get_embeddings", lambda _spec: stub)

    with pytest.raises(LlmError) as exc:
        LlmClient().embed(["a"], model="stub:model")

    assert exc.value.kind == "auth"
    assert stub.calls == 1


def test_embed_gives_up_after_max_attempts(monkeypatch):
    stub = _FlakyEmbeddings(fail_times=99, error_message="upstream timeout")
    monkeypatch.setattr(llm, "_get_embeddings", lambda _spec: stub)

    with pytest.raises(LlmError) as exc:
        LlmClient().embed(["a"], model="stub:model")

    assert exc.value.kind == "timeout"
    assert stub.calls == 3
