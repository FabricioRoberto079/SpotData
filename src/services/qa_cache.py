from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from src.data.chroma_client import get_chroma_client
from src.interfaces.qa_cache import IQaCache, normalize_question, question_key

logger = logging.getLogger(__name__)

QA_CACHE_L1_MAX_ENTRIES = 256
QA_CACHE_L2_COLLECTION = "qa_cache"
QA_CACHE_L2_DISTANCE_THRESHOLD = 0.2
QA_CACHE_L2_LOOKUP_NEIGHBORS = 1


@dataclass
class _L1Entry:
    payload: dict[str, Any]
    hits: int = 0
    last_access: float = field(default_factory=time.monotonic)


class HybridQaCache(IQaCache):
    def __init__(
        self,
        l1_max_entries: int = QA_CACHE_L1_MAX_ENTRIES,
        l2_threshold: float = QA_CACHE_L2_DISTANCE_THRESHOLD,
        l2_collection_name: str = QA_CACHE_L2_COLLECTION,
    ) -> None:
        if l1_max_entries <= 0:
            raise ValueError("l1_max_entries must be positive")
        self._l1_max = l1_max_entries
        self._l2_threshold = l2_threshold
        self._l2_collection_name = l2_collection_name
        self._l1: dict[str, _L1Entry] = {}
        self._l1_lock = threading.Lock()
        self._l2_lock = threading.Lock()
        self._generation = 0
        self._l1_hits = 0
        self._l2_hits = 0
        self._misses = 0

    def _l2_collection(self):
        try:
            return get_chroma_client().get_or_create_collection(
                name=self._l2_collection_name
            )
        except Exception:
            logger.exception("Semantic cache: failed to access collection")
            return None

    def lookup_exact(self, question: str) -> dict[str, Any] | None:
        key = question_key(question)
        with self._l1_lock:
            entry = self._l1.get(key)
            if entry is None:
                return None
            entry.hits += 1
            entry.last_access = time.monotonic()
            self._l1_hits += 1
            return dict(entry.payload)

    def lookup_semantic(
        self, question: str, embedding: list[float]
    ) -> dict[str, Any] | None:
        col = self._l2_collection()
        if col is None:
            self._record_miss()
            return None

        try:
            res = col.query(
                query_embeddings=[embedding],
                n_results=QA_CACHE_L2_LOOKUP_NEIGHBORS,
            )
        except Exception:
            logger.exception("Semantic cache: query failed")
            self._record_miss()
            return None

        ids = res.get("ids") or [[]]
        if not ids[0]:
            self._record_miss()
            return None

        distance = res["distances"][0][0]
        if distance > self._l2_threshold:
            self._record_miss()
            return None

        raw = res["metadatas"][0][0].get("payload") if res.get("metadatas") else None
        if not raw:
            self._record_miss()
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Semantic cache: corrupt payload; ignoring entry")
            self._record_miss()
            return None

        self._put_l1(question, payload)
        with self._l1_lock:
            self._l2_hits += 1
        return dict(payload)

    def _record_miss(self) -> None:
        with self._l1_lock:
            self._misses += 1

    def _put_l1(self, question: str, payload: dict[str, Any]) -> None:
        key = question_key(question)
        with self._l1_lock:
            existing = self._l1.get(key)
            if existing is not None:
                existing.payload = payload
                existing.last_access = time.monotonic()
                return
            if len(self._l1) >= self._l1_max:
                victim_key = min(
                    self._l1.items(),
                    key=lambda kv: (kv[1].hits, kv[1].last_access),
                )[0]
                self._l1.pop(victim_key, None)
            self._l1[key] = _L1Entry(payload=payload)

    def put(
        self,
        question: str,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None:
        self._put_l1(question, payload)
        col = self._l2_collection()
        if col is None:
            return
        try:
            col.upsert(
                ids=[question_key(question)],
                embeddings=[embedding],
                documents=[normalize_question(question)],
                metadatas=[{"payload": json.dumps(payload)}],
            )
        except Exception:
            logger.exception("Semantic cache: upsert failed")

    def invalidate_all(self) -> None:
        with self._l1_lock:
            self._l1.clear()
            self._generation += 1
        with self._l2_lock:
            try:
                get_chroma_client().delete_collection(self._l2_collection_name)
            except Exception:
                logger.exception("Semantic cache: delete_collection failed")

    def stats(self) -> dict[str, Any]:
        with self._l1_lock:
            l1_top = sorted(
                self._l1.values(),
                key=lambda e: (e.hits, e.last_access),
                reverse=True,
            )[:10]
            total = self._l1_hits + self._l2_hits + self._misses
            hit_ratio = (
                (self._l1_hits + self._l2_hits) / total if total else 0.0
            )
            data: dict[str, Any] = {
                "l1_size": len(self._l1),
                "l1_max": self._l1_max,
                "l1_hits": self._l1_hits,
                "l2_hits": self._l2_hits,
                "misses": self._misses,
                "hit_ratio": round(hit_ratio, 4),
                "generation": self._generation,
                "l2_threshold": self._l2_threshold,
                "l1_top": [
                    {"hits": e.hits, "question": e.payload.get("question")}
                    for e in l1_top
                ],
            }
        col = self._l2_collection()
        if col is None:
            data["l2_size"] = None
        else:
            try:
                data["l2_size"] = col.count()
            except Exception:
                logger.exception("Semantic cache: count failed")
                data["l2_size"] = None
        return data


_instance: IQaCache | None = None
_instance_lock = threading.Lock()


def get_qa_cache() -> IQaCache:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = HybridQaCache()
    return _instance


def reset_qa_cache() -> None:
    global _instance
    with _instance_lock:
        _instance = None
