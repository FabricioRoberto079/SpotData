from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, TypeVar

from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class LlmError(Exception):
    kind: str
    status_code: int
    detail: str
    cause: Exception | None = None

    def __str__(self) -> str:
        return f"[{self.kind}] {self.detail}"


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _resolve_chat_spec(model: str | None, *, structured: bool = False) -> str:
    if model:
        return model
    if structured:
        spec = os.getenv("LLM_STRUCTURED_MODEL")
        if spec:
            return spec
    return _required_env("LLM_CHAT_MODEL")


def _resolve_embedding_spec(model: str | None) -> str:
    return model or _required_env("LLM_EMBEDDING_MODEL")


@lru_cache(maxsize=8)
def _get_chat_model(
    spec: str, temperature: float, max_tokens: int | None
) -> BaseChatModel:
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


def _classify(exc: Exception) -> LlmError:
    msg = str(exc)
    lower = msg.lower()
    if "quota" in lower or "rate limit" in lower or "429" in lower:
        return LlmError("rate_limit", 429, "LLM rate limit reached.", exc)
    if (
        "unauthorized" in lower
        or "permission" in lower
        or "401" in lower
        or "403" in lower
        or "api key" in lower
        or "authentication" in lower
    ):
        return LlmError("auth", 502, "Invalid API key or no permission.", exc)
    if "timeout" in lower or "deadline" in lower:
        return LlmError("timeout", 504, "Timeout calling LLM provider.", exc)
    if "not found" in lower or "404" in lower:
        return LlmError("model_not_found", 502, "Model not found on provider.", exc)
    if "content_filter" in lower or "content filter" in lower or "blocked" in lower:
        return LlmError(
            "content_filter", 502, "Response blocked by content filter.", exc
        )
    if "invalid" in lower or "400" in lower:
        return LlmError("bad_request", 400, f"Invalid request: {exc}", exc)
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


class LlmClient:
    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        llm = _get_chat_model(_resolve_chat_spec(model), temperature, max_tokens)
        result = _wrap(lambda: llm.invoke(_convert_messages(messages)))
        content = getattr(result, "content", None)
        if not content:
            raise LlmError("empty", 502, "Empty response from model.")
        return content if isinstance(content, str) else str(content)

    def chat_structured(
        self,
        messages: list[dict],
        response_model: type[T],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> T:
        llm = _get_chat_model(
            _resolve_chat_spec(model, structured=True), temperature, max_tokens
        )
        structured = llm.with_structured_output(response_model)
        result = _wrap(lambda: structured.invoke(_convert_messages(messages)))

        if isinstance(result, response_model):
            return result
        if isinstance(result, dict):
            try:
                return response_model.model_validate(result)
            except ValidationError as e:
                raise LlmError(
                    "schema", 502, f"Response does not match schema: {e}", e
                ) from e
        raise LlmError("schema", 502, "Invalid structured response.")

    def embed(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []
        embeddings = _get_embeddings(_resolve_embedding_spec(model))
        result = _wrap(lambda: embeddings.embed_documents(list(texts)))
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


def reset_llm_client() -> None:
    global _client_singleton
    _client_singleton = None
    _get_chat_model.cache_clear()
    _get_embeddings.cache_clear()
