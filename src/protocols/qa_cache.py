from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from typing import Any

_whitespace = re.compile(r"\s+")


def normalize_question(question: str) -> str:
    return _whitespace.sub(" ", (question or "").strip().lower())


def question_key(question: str, category_id: str | None = None) -> str:
    """Cache key for a question under a retrieval scope.

    The scope (``category_id``; ``None`` for the global, search-everything chats)
    is folded into the hash, so the same question cached for different categories
    never collides. A category-scoped chat can therefore only ever read back an
    answer computed for its own scope, which keeps category-restricted content
    from leaking across categories."""
    scope = category_id or ""
    basis = f"{scope}\x00{normalize_question(question)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


class IQaCache(ABC):
    @abstractmethod
    def lookup_exact(
        self, question: str, category_id: str | None = None
    ) -> dict[str, Any] | None: ...

    @abstractmethod
    def lookup_semantic(
        self,
        question: str,
        embedding: list[float],
        category_id: str | None = None,
    ) -> dict[str, Any] | None: ...

    @abstractmethod
    def put(
        self,
        question: str,
        embedding: list[float],
        payload: dict[str, Any],
        category_id: str | None = None,
    ) -> None: ...

    @abstractmethod
    def invalidate_all(self) -> None: ...

    @abstractmethod
    def invalidate_category(self, category_id: str | None) -> None: ...

    @abstractmethod
    def stats(self) -> dict[str, Any]: ...
