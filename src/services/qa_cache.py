from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, func, or_, select

from src.data.postgres_client import SessionLocal
from src.interfaces.qa_cache import IQaCache, normalize_question, question_key
from src.models.qa_cache_entry import QaCacheEntry

logger = logging.getLogger(__name__)

QA_CACHE_L1_MAX_ENTRIES = 256
QA_CACHE_L2_DISTANCE_THRESHOLD = 0.2
QA_CACHE_L2_LOOKUP_NEIGHBORS = 1


@dataclass
class _L1Entry:
    payload: dict[str, Any]
    scope: str | None = None
    hits: int = 0
    last_access: float = field(default_factory=time.monotonic)


class HybridQaCache(IQaCache):
    def __init__(
        self,
        l1_max_entries: int = QA_CACHE_L1_MAX_ENTRIES,
        l2_threshold: float = QA_CACHE_L2_DISTANCE_THRESHOLD,
    ) -> None:
        if l1_max_entries <= 0:
            raise ValueError("l1_max_entries must be positive")
        self._l1_max = l1_max_entries
        self._l2_threshold = l2_threshold
        self._l1: dict[str, _L1Entry] = {}
        self._l1_lock = threading.Lock()
        self._generation = 0
        self._l1_hits = 0
        self._l2_hits = 0
        self._misses = 0

    def lookup_exact(self, question: str, category_id: str | None = None) -> dict[str, Any] | None:
        key = question_key(question, category_id)
        with self._l1_lock:
            entry = self._l1.get(key)
            if entry is None:
                return None
            entry.hits += 1
            entry.last_access = time.monotonic()
            self._l1_hits += 1
            return dict(entry.payload)

    def _put_l1(self, question: str, payload: dict[str, Any], category_id: str | None) -> None:
        key = question_key(question, category_id)
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
            self._l1[key] = _L1Entry(payload=payload, scope=category_id)

    def _record_miss(self) -> None:
        with self._l1_lock:
            self._misses += 1

    def lookup_semantic(
        self,
        question: str,
        embedding: list[float],
        category_id: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            with SessionLocal() as session:
                distance = QaCacheEntry.embedding.cosine_distance(embedding)
                scope = (
                    QaCacheEntry.category_id.is_(None)
                    if category_id is None
                    else QaCacheEntry.category_id == category_id
                )
                row = session.execute(
                    select(QaCacheEntry, distance.label("distance"))
                    .where(scope)
                    .order_by(distance.asc())
                    .limit(QA_CACHE_L2_LOOKUP_NEIGHBORS)
                ).first()
        except Exception:
            logger.exception("Semantic cache: query failed")
            self._record_miss()
            return None

        if row is None:
            self._record_miss()
            return None

        entry, dist = row
        if float(dist) > self._l2_threshold:
            self._record_miss()
            return None

        payload = entry.payload
        if not isinstance(payload, dict):
            logger.warning("Semantic cache: corrupt payload; ignoring entry")
            self._record_miss()
            return None

        self._put_l1(question, payload, category_id)
        with self._l1_lock:
            self._l2_hits += 1
        return dict(payload)

    def put(
        self,
        question: str,
        embedding: list[float],
        payload: dict[str, Any],
        category_id: str | None = None,
    ) -> None:
        self._put_l1(question, payload, category_id)
        key = question_key(question, category_id)
        try:
            with SessionLocal() as session:
                existing = session.get(QaCacheEntry, key)
                if existing is None:
                    session.add(
                        QaCacheEntry(
                            question_key=key,
                            category_id=category_id,
                            normalized_question=normalize_question(question),
                            payload=payload,
                            embedding=embedding,
                        )
                    )
                else:
                    existing.category_id = category_id
                    existing.normalized_question = normalize_question(question)
                    existing.payload = payload
                    existing.embedding = embedding
                session.commit()
        except Exception:
            logger.exception("Semantic cache: upsert failed")

    def invalidate_all(self) -> None:
        with self._l1_lock:
            self._l1.clear()
            self._generation += 1
        try:
            with SessionLocal() as session:
                session.execute(delete(QaCacheEntry))
                session.commit()
        except Exception:
            logger.exception("Semantic cache: invalidate_all failed")

    def invalidate_category(self, category_id: str | None) -> None:
        """Drop cached answers affected by a change to documents in ``category_id``.

        Uncategorized documents (``category_id`` NULL) are shared and surface in
        every search, so a change to one invalidates the whole cache. A change to
        a real category X invalidates that category's entries plus the global
        (scope-less) ones, which may have drawn on X; entries scoped to other
        categories are left untouched."""
        if category_id is None:
            self.invalidate_all()
            return
        with self._l1_lock:
            stale = [
                key
                for key, entry in self._l1.items()
                if entry.scope == category_id or entry.scope is None
            ]
            for key in stale:
                self._l1.pop(key, None)
            self._generation += 1
        try:
            with SessionLocal() as session:
                session.execute(
                    delete(QaCacheEntry).where(
                        or_(
                            QaCacheEntry.category_id == category_id,
                            QaCacheEntry.category_id.is_(None),
                        )
                    )
                )
                session.commit()
        except Exception:
            logger.exception("Semantic cache: invalidate_category failed")

    def stats(self) -> dict[str, Any]:
        with self._l1_lock:
            l1_top = sorted(
                self._l1.values(),
                key=lambda e: (e.hits, e.last_access),
                reverse=True,
            )[:10]
            total = self._l1_hits + self._l2_hits + self._misses
            hit_ratio = (self._l1_hits + self._l2_hits) / total if total else 0.0
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
                    {
                        "hits": e.hits,
                        "scope": e.scope,
                        "question": e.payload.get("question"),
                    }
                    for e in l1_top
                ],
            }
        try:
            with SessionLocal() as session:
                data["l2_size"] = session.execute(
                    select(func.count()).select_from(QaCacheEntry)
                ).scalar_one()
        except Exception:
            logger.exception("Semantic cache: stats count failed")
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
