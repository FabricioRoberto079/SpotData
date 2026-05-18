from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from typing import Any

_whitespace = re.compile(r"\s+")


def normalize_question(question: str) -> str:
    return _whitespace.sub(" ", (question or "").strip().lower())


def question_key(question: str) -> str:
    return hashlib.sha256(normalize_question(question).encode("utf-8")).hexdigest()


class IQaCache(ABC):
    @abstractmethod
    def lookup_exact(self, question: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def lookup_semantic(
        self, question: str, embedding: list[float]
    ) -> dict[str, Any] | None: ...

    @abstractmethod
    def put(
        self,
        question: str,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None: ...

    @abstractmethod
    def invalidate_all(self) -> None: ...

    @abstractmethod
    def stats(self) -> dict[str, Any]: ...
