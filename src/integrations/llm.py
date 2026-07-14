from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.utils.function_calling import convert_to_openai_function
from pydantic import ValidationError

from src.config import required_env

logger = logging.getLogger(__name__)


@dataclass
class LlmError(Exception):
    kind: str
    status_code: int
    detail: str
    cause: Exception | None = None

    def __str__(self) -> str:
        return f"[{self.kind}] {self.detail}"


def _resolve_chat_spec(model: str | None, *, structured: bool = False) -> str:
    if model:
        return model
    if structured:
        spec = os.getenv("LLM_STRUCTURED_MODEL")
        if spec:
            return spec
    return required_env("LLM_CHAT_MODEL")


def _resolve_embedding_spec(model: str | None) -> str:
    return model or required_env("LLM_EMBEDDING_MODEL")


@lru_cache(maxsize=8)
def _get_chat_model(spec: str, temperature: float, max_tokens: int | None) -> BaseChatModel:
    try:
        kwargs: dict = {"temperature": temperature}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return init_chat_model(spec, **kwargs)
    except Exception as exc:
        raise LlmError(
            "config", 503, f"Failed to initialize chat model {spec!r}: {exc}", exc
        ) from exc


@lru_cache(maxsize=4)
def _get_embeddings(spec: str) -> Embeddings:
    try:
        return init_embeddings(spec)
    except Exception as exc:
        raise LlmError(
            "config", 503, f"Failed to initialize embeddings {spec!r}: {exc}", exc
        ) from exc


def _convert_messages(messages: list[dict]) -> list[BaseMessage]:
    converted: list[BaseMessage] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "assistant":
            converted.append(AIMessage(content=content))
        else:
            converted.append(HumanMessage(content=content))
    return converted


_CLASSIFY_RULES: tuple[tuple[tuple[str, ...], str, int, str], ...] = (
    (("quota", "rate limit", "429"), "rate_limit", 429, "LLM rate limit reached."),
    (
        ("unauthorized", "permission", "401", "403", "api key", "authentication"),
        "auth",
        502,
        "Invalid API key or no permission.",
    ),
    (("timeout", "deadline"), "timeout", 504, "Timeout calling LLM provider."),
    (("not found", "404"), "model_not_found", 502, "Model not found on provider."),
    (
        ("content_filter", "content filter", "blocked"),
        "content_filter",
        502,
        "Response blocked by content filter.",
    ),
    (("invalid", "400"), "bad_request", 400, "Invalid request: {exc}"),
)


def _classify(exc: Exception) -> LlmError:
    lower = str(exc).lower()
    for markers, kind, status, detail in _CLASSIFY_RULES:
        if any(marker in lower for marker in markers):
            return LlmError(kind, status, detail.format(exc=exc), exc)
    return LlmError("provider", 502, f"LLM provider error: {exc}", exc)


def _wrap(call: Callable):
    try:
        return call()
    except LlmError:
        raise
    except ValidationError as e:
        raise LlmError("schema", 502, f"Response does not match schema: {e}", e) from e
    except Exception as e:
        raise _classify(e) from e


_RETRYABLE_KINDS = {"rate_limit", "timeout", "provider"}
_EMBED_MAX_ATTEMPTS = 3
_EMBED_BACKOFF_SECONDS = (0.5, 2.0)


def _embed_with_retry(embeddings: Embeddings, texts: list[str]) -> list[list[float]]:
    """Call embed_documents, retrying transient failures with backoff. A single
    flaky 429/timeout no longer aborts a whole document ingestion."""
    last_error: LlmError | None = None
    for attempt in range(_EMBED_MAX_ATTEMPTS):
        try:
            return embeddings.embed_documents(list(texts))
        except LlmError as err:
            last_error = err
            retryable = err.kind in _RETRYABLE_KINDS
        except Exception as exc:
            last_error = _classify(exc)
            retryable = last_error.kind in _RETRYABLE_KINDS
        if not retryable or attempt == _EMBED_MAX_ATTEMPTS - 1:
            raise last_error
        wait = _EMBED_BACKOFF_SECONDS[min(attempt, len(_EMBED_BACKOFF_SECONDS) - 1)]
        logger.warning(
            "Embedding call failed (%s); retrying in %.1fs (attempt %d/%d).",
            last_error.kind,
            wait,
            attempt + 1,
            _EMBED_MAX_ATTEMPTS,
        )
        time.sleep(wait)
    assert last_error is not None
    raise last_error


class LlmClient:
    async def chat_stream_structured(
        self,
        messages: list[dict],
        schema: Any,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[dict]:
        """Stream cumulative snapshots of the structured response, always as
        plain dicts — provider differences (dict partials on the OpenAI path,
        Pydantic partials elsewhere) are normalized here."""
        spec = _resolve_chat_spec(model, structured=True)
        llm = _get_chat_model(spec, temperature, max_tokens)

        schema_arg: Any = schema
        if spec.startswith("openai:") and isinstance(schema, type):
            fn = convert_to_openai_function(schema, strict=True)
            schema_arg = {
                "name": fn["name"],
                "schema": fn["parameters"],
                "strict": True,
            }
            if "description" in fn:
                schema_arg["description"] = fn["description"]

        if spec.startswith("openai:"):
            try:
                structured = llm.with_structured_output(schema_arg, strict=True)
            except TypeError:
                structured = llm.with_structured_output(schema_arg)
        else:
            structured = llm.with_structured_output(schema)
        converted = _convert_messages(messages)

        try:
            async for partial in structured.astream(converted):
                if isinstance(partial, dict):
                    yield partial
                elif hasattr(partial, "model_dump"):
                    yield partial.model_dump()
        except LlmError:
            raise
        except Exception as e:
            raise _classify(e) from e

    def embed(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []
        embeddings = _get_embeddings(_resolve_embedding_spec(model))
        result = _embed_with_retry(embeddings, texts)
        if not result or len(result) != len(texts):
            raise LlmError(
                "empty",
                502,
                f"Embeddings missing or wrong count (expected {len(texts)}).",
            )
        return [list(vec) for vec in result]


_client_singleton: LlmClient | None = None


def get_llm_client() -> LlmClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = LlmClient()
    return _client_singleton
