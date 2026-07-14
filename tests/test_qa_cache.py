from src.protocols.qa_cache import normalize_question, question_key
from src.services.qa_cache import HybridQaCache


def _make(monkeypatch, l1_max_entries: int = 4):
    class _NoSession:
        def __enter__(self):
            raise RuntimeError("db offline in test")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("src.services.qa_cache.SessionLocal", lambda: _NoSession())
    return HybridQaCache(l1_max_entries=l1_max_entries)


def test_normalize_collapses_whitespace_and_case():
    assert normalize_question("  Qual  É a META?\n") == "qual é a meta?"


def test_question_key_is_stable_for_equivalent_inputs():
    assert question_key("Qual é a meta?") == question_key("  qual é a META?  ")


def test_l1_hit_returns_payload_and_increments_hits(monkeypatch):
    cache = _make(monkeypatch)
    cache.put("Qual é a meta?", [0.1] * 4, {"answer": "X"})
    assert cache.lookup_exact("qual é a META?") == {"answer": "X"}
    stats = cache.stats()
    assert stats["l1_hits"] == 1
    assert stats["misses"] == 0


def test_l1_miss_records_and_returns_none(monkeypatch):
    cache = _make(monkeypatch)
    assert cache.lookup_exact("pergunta nova") is None
    assert cache.stats()["l1_hits"] == 0


def test_lfu_eviction_drops_least_frequent(monkeypatch):
    cache = _make(monkeypatch, l1_max_entries=2)
    cache.put("popular", [0.1] * 4, {"answer": "p"})
    cache.put("rara", [0.1] * 4, {"answer": "r"})
    for _ in range(5):
        cache.lookup_exact("popular")

    cache.put("nova", [0.1] * 4, {"answer": "n"})
    assert cache.lookup_exact("rara") is None
    assert cache.lookup_exact("popular") == {"answer": "p"}
    assert cache.lookup_exact("nova") == {"answer": "n"}


def test_invalidate_all_clears_l1_and_bumps_generation(monkeypatch):
    cache = _make(monkeypatch)
    cache.put("q1", [0.1] * 4, {"answer": "a"})
    gen0 = cache.stats()["generation"]
    cache.invalidate_all()
    assert cache.lookup_exact("q1") is None
    assert cache.stats()["generation"] == gen0 + 1


def test_semantic_lookup_degrades_gracefully_without_db(monkeypatch):
    cache = _make(monkeypatch)
    assert cache.lookup_semantic("q", [0.1] * 4) is None
    assert cache.stats()["misses"] == 1


def test_question_key_differs_by_scope_but_stable_within_one():
    assert question_key("q") != question_key("q", "cat-a")
    assert question_key("q", "cat-a") != question_key("q", "cat-b")
    assert question_key("Qual é a meta?", "cat-a") == question_key("  qual é a META?  ", "cat-a")


def test_l1_lookup_is_isolated_by_scope(monkeypatch):
    cache = _make(monkeypatch)
    cache.put("qual a meta?", [0.1] * 4, {"answer": "global"})
    cache.put("qual a meta?", [0.1] * 4, {"answer": "cat-a"}, "cat-a")

    assert cache.lookup_exact("qual a meta?") == {"answer": "global"}
    assert cache.lookup_exact("qual a meta?", "cat-a") == {"answer": "cat-a"}
    assert cache.lookup_exact("qual a meta?", "cat-b") is None


def test_invalidate_category_drops_scope_and_global_keeps_other_categories(monkeypatch):
    cache = _make(monkeypatch)
    cache.put("q", [0.1] * 4, {"answer": "g"})
    cache.put("q", [0.1] * 4, {"answer": "a"}, "cat-a")
    cache.put("q", [0.1] * 4, {"answer": "b"}, "cat-b")

    cache.invalidate_category("cat-a")

    assert cache.lookup_exact("q", "cat-a") is None
    assert cache.lookup_exact("q") is None
    assert cache.lookup_exact("q", "cat-b") == {"answer": "b"}


def test_invalidate_category_none_clears_everything(monkeypatch):
    cache = _make(monkeypatch)
    cache.put("q", [0.1] * 4, {"answer": "g"})
    cache.put("q", [0.1] * 4, {"answer": "a"}, "cat-a")
    gen0 = cache.stats()["generation"]

    cache.invalidate_category(None)

    assert cache.lookup_exact("q") is None
    assert cache.lookup_exact("q", "cat-a") is None
    assert cache.stats()["generation"] == gen0 + 1


def test_put_with_stale_generation_is_skipped(monkeypatch):
    cache = _make(monkeypatch)
    stale = cache.generation()
    cache.invalidate_category("cat-x")
    cache.put("pergunta", [0.1] * 4, {"answer": "velha"}, generation=stale)
    assert cache.lookup_exact("pergunta") is None


def test_put_with_current_generation_is_stored(monkeypatch):
    cache = _make(monkeypatch)
    cache.put("pergunta", [0.1] * 4, {"answer": "nova"}, generation=cache.generation())
    assert cache.lookup_exact("pergunta") == {"answer": "nova"}
