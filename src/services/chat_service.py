from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.data.postgres_client import get_session
from src.enums.response_status import ResponseStatus
from src.exceptions import NotFoundError, ValidationError
from src.integrations.llm import LlmClient, LlmError, get_llm_client
from src.interfaces.chat_service import IChatService
from src.interfaces.qa_cache import IQaCache
from src.interfaces.vector_index_service import IVectorIndexService
from src.models.chat import Chat
from src.models.chat_folder import ChatFolder
from src.models.document_version import DocumentVersion
from src.models.evidence_citation import EvidenceCitation
from src.models.knowledge_document import KnowledgeDocument
from src.models.query import Query
from src.models.response import Response as ResponseModel
from src.prompts.rag_prompt import RagAnswer, build_messages
from src.services.qa_cache import get_qa_cache
from src.services.vector_index_service import get_vector_index_service

logger = logging.getLogger(__name__)

CHAT_HISTORY_LIMIT = 10
CHAT_TITLE_MAX_CHARS = 60
RAG_TOP_K = 10

MIN_CITATION_CONFIDENCE = 0.6


class ChatService(IChatService):
    def __init__(
        self,
        session: Session,
        vector_index: IVectorIndexService,
        llm_client: LlmClient,
        cache: IQaCache,
    ) -> None:
        self._session = session
        self._vector_index = vector_index
        self._llm = llm_client
        self._cache = cache

    @staticmethod
    def _serialize(chat: Chat) -> dict:
        return {
            "id": chat.id,
            "title": chat.title,
            "folder_id": chat.folder_id,
            "user_id": chat.user_id,
            "created_at": chat.created_at.isoformat() if chat.created_at else None,
        }

    def _ensure_folder_owned(
        self, folder_id: str | None, user_id: str | None
    ) -> None:
        if folder_id is None:
            return
        folder = self._session.get(ChatFolder, folder_id)
        if folder is None:
            raise NotFoundError(f"Chat folder not found: {folder_id}")
        if (
            user_id is not None
            and folder.owner_id is not None
            and folder.owner_id != user_id
        ):
            raise NotFoundError(f"Chat folder not found: {folder_id}")

    def _load_owned(self, chat_id: str, user_id: str | None) -> Chat:
        """Load a chat or raise NotFoundError. When user_id is given, treats chats
        owned by other users as if they did not exist (avoids leaking existence)."""
        chat = self._session.get(Chat, chat_id)
        if chat is None:
            raise NotFoundError(f"Chat not found: {chat_id}")
        if user_id is not None and chat.user_id is not None and chat.user_id != user_id:
            raise NotFoundError(f"Chat not found: {chat_id}")
        return chat

    def list(
        self, folder_id: str | None = None, user_id: str | None = None
    ) -> list[dict]:
        stmt = select(Chat)
        if folder_id is not None:
            stmt = stmt.where(Chat.folder_id == folder_id)
        if user_id is not None:
            stmt = stmt.where(Chat.user_id == user_id)
        stmt = stmt.order_by(Chat.created_at.desc(), Chat.id.desc())
        items = self._session.execute(stmt).scalars().all()
        return [self._serialize(c) for c in items]

    def get(self, chat_id: str, user_id: str | None = None) -> dict:
        chat = self._load_owned(chat_id, user_id)
        payload = self._serialize(chat)
        payload["messages"] = self._serialize_messages(chat_id)
        return payload

    def _serialize_messages(self, chat_id: str) -> list[dict]:
        stmt = (
            select(Query)
            .where(Query.chat_id == chat_id)
            .options(
                selectinload(Query.response).selectinload(ResponseModel.citations)
            )
            .order_by(Query.created_at.asc())
        )
        queries = self._session.execute(stmt).scalars().all()

        document_ids: set[str] = set()
        for q in queries:
            if q.response is None:
                continue
            for c in q.response.citations:
                document_ids.add(c.document_id)
        docs_by_id: dict[str, KnowledgeDocument] = {}
        if document_ids:
            doc_rows = self._session.execute(
                select(KnowledgeDocument)
                .options(selectinload(KnowledgeDocument.versions))
                .where(KnowledgeDocument.id.in_(document_ids))
            ).scalars().all()
            docs_by_id = {d.id: d for d in doc_rows}

        messages: list[dict] = []
        for q in queries:
            messages.append(
                {
                    "id": q.id,
                    "role": "user",
                    "content": q.question,
                    "created_at": q.created_at.isoformat() if q.created_at else None,
                    "status": None,
                    "citations": [],
                    "time_ms": None,
                }
            )
            response = q.response
            if response is None:
                continue
            messages.append(
                {
                    "id": response.id,
                    "role": "assistant",
                    "content": response.response_text,
                    "created_at": (
                        response.created_at.isoformat()
                        if response.created_at
                        else None
                    ),
                    "status": response.status,
                    "citations": [
                        self._serialize_citation_with_doc(c, docs_by_id.get(c.document_id))
                        for c in response.citations
                    ],
                    "time_ms": response.time_ms,
                }
            )
        return messages

    @staticmethod
    def _serialize_citation_with_doc(
        citation: EvidenceCitation,
        doc: "KnowledgeDocument | None",
    ) -> dict:
        version = None
        if doc is not None and citation.document_version_id is not None:
            version = next(
                (v for v in doc.versions if v.id == citation.document_version_id),
                None,
            )
        return {
            "document_id": citation.document_id,
            "document_version_id": version.id if version else None,
            "version_number": version.version_number if version else None,
            "file_name": doc.file_name if doc else None,
            "page": citation.page,
            "excerpt": citation.used_excerpt,
            "confidence_score": citation.confidence_score,
            "download_url": (
                f"/documents/{citation.document_id}/download" if doc else None
            ),
        }

    def update(
        self, chat_id: str, fields: dict, user_id: str | None = None
    ) -> dict:
        try:
            chat = self._load_owned(chat_id, user_id)
            if "folder_id" in fields:
                self._ensure_folder_owned(fields["folder_id"], user_id)
                chat.folder_id = fields["folder_id"]
            if "title" in fields and fields["title"] is not None:
                chat.title = fields["title"]
            self._session.commit()
            self._session.refresh(chat)
            return self._serialize(chat)
        except Exception:
            self._session.rollback()
            raise

    def delete(self, chat_id: str, user_id: str | None = None) -> None:
        try:
            chat = self._load_owned(chat_id, user_id)
            self._session.delete(chat)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def _resolve_version(
        self, document_id: str, version_number: int | None
    ) -> "DocumentVersion | None":
        doc = self._session.get(KnowledgeDocument, document_id)
        if doc is None or not doc.versions:
            return None
        if version_number is None:
            return max(doc.versions, key=lambda v: v.version_number)
        for v in doc.versions:
            if v.version_number == version_number:
                return v
        return None

    def _serialize_citation(
        self,
        citation: EvidenceCitation,
        version: "DocumentVersion | None" = None,
    ) -> dict:
        doc = self._session.get(KnowledgeDocument, citation.document_id)
        if version is None and citation.document_version_id is not None:
            version = next(
                (
                    v
                    for v in (doc.versions if doc else [])
                    if v.id == citation.document_version_id
                ),
                None,
            )
        return {
            "document_id": citation.document_id,
            "document_version_id": version.id if version else None,
            "version_number": version.version_number if version else None,
            "file_name": doc.file_name if doc else None,
            "page": citation.page,
            "excerpt": citation.used_excerpt,
            "confidence_score": citation.confidence_score,
            "download_url": (
                f"/documents/{citation.document_id}/download" if doc else None
            ),
        }

    @staticmethod
    def _clamp_confidence(raw) -> float | None:
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if value != value:
            return None
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    def _persist_citation_by_context(
        self,
        context_index: int,
        confidence: float,
        contexts: list[dict],
        response_id: str,
    ) -> dict | None:
        if context_index < 0 or context_index >= len(contexts):
            return None
        ctx = contexts[context_index]
        document_id = ctx.get("document_id")
        if not document_id:
            return None
        doc = self._session.get(KnowledgeDocument, document_id)
        if doc is None:
            return None
        version = self._resolve_version(document_id, ctx.get("version_number"))
        snippet = ctx.get("snippet") or ""
        if not snippet.strip():
            return None
        citation_row = EvidenceCitation(
            response_id=response_id,
            document_id=document_id,
            document_version_id=version.id if version else None,
            page=ctx.get("page"),
            used_excerpt=snippet,
            confidence_score=confidence,
        )
        self._session.add(citation_row)
        self._session.flush()
        return self._serialize_citation(citation_row, version=version)

    @staticmethod
    def _chat_title_from_question(question: str) -> str:
        text = question.strip().splitlines()[0].strip() if question else ""
        if not text:
            return "New chat"
        if len(text) > CHAT_TITLE_MAX_CHARS:
            return text[: CHAT_TITLE_MAX_CHARS - 3].rstrip() + "..."
        return text

    def _resolve_or_create_chat(
        self, chat_id: str | None, question: str, user_id: str | None
    ) -> str:
        if chat_id is not None:
            self._load_owned(chat_id, user_id)
            return chat_id
        chat = Chat(
            title=self._chat_title_from_question(question),
            user_id=user_id,
        )
        self._session.add(chat)
        self._session.flush()
        return chat.id

    def _load_chat_history(self, chat_id: str) -> list[dict]:
        stmt = (
            select(Query)
            .where(Query.chat_id == chat_id)
            .order_by(Query.created_at.desc())
            .limit(CHAT_HISTORY_LIMIT)
        )
        queries = list(self._session.execute(stmt).scalars().all())
        queries.reverse()

        history: list[dict] = []
        for q in queries:
            if q.response is None or not q.response.response_text:
                continue
            history.append({"role": "user", "content": q.question})
            history.append(
                {"role": "assistant", "content": q.response.response_text}
            )
        return history

    @staticmethod
    def _is_valid_cached_payload(payload: dict) -> bool:
        if payload.get("status") != ResponseStatus.SUCCESS.value:
            return False
        answer = (payload.get("answer") or "").strip()
        if not answer:
            return False
        if not payload.get("citations"):
            return False
        return True

    @staticmethod
    def _build_stream_cache_payload(
        question: str, answer: str, citations: list[dict]
    ) -> dict:
        return {
            "question": question,
            "answer": answer,
            "status": ResponseStatus.SUCCESS.value,
            "citations": [
                {
                    "document_id": c["document_id"],
                    "version_number": c.get("version_number"),
                    "excerpt": c["excerpt"],
                    "confidence_score": c["confidence_score"],
                    "page": c.get("page"),
                }
                for c in citations
            ],
        }

    async def _serve_cached_stream(
        self,
        question: str,
        cached: dict,
        user_id: str | None,
        chat_id: str | None,
        started: float,
    ) -> AsyncIterator[dict]:
        try:
            chat_id = self._resolve_or_create_chat(chat_id, question, user_id)
            query_row = Query(user_id=user_id, chat_id=chat_id, question=question)
            self._session.add(query_row)
            self._session.flush()

            response_row = ResponseModel(
                query_id=query_row.id,
                response_text=cached["answer"],
                status=cached["status"],
                time_ms=0,
            )
            self._session.add(response_row)
            self._session.flush()

            yield {
                "type": "meta",
                "chat_id": chat_id,
                "query_id": query_row.id,
                "response_id": response_row.id,
            }

            citations_payload: list[dict] = []
            if cached["status"] == ResponseStatus.SUCCESS.value:
                for c in cached.get("citations", []):
                    doc = self._session.get(KnowledgeDocument, c["document_id"])
                    if doc is None:
                        continue
                    confidence = self._clamp_confidence(c.get("confidence_score"))
                    if confidence is None:
                        continue
                    version = self._resolve_version(
                        c["document_id"], c.get("version_number")
                    )
                    citation_row = EvidenceCitation(
                        response_id=response_row.id,
                        document_id=c["document_id"],
                        document_version_id=version.id if version else None,
                        page=c.get("page"),
                        used_excerpt=c["excerpt"],
                        confidence_score=confidence,
                    )
                    self._session.add(citation_row)
                    self._session.flush()
                    payload = self._serialize_citation(citation_row, version=version)
                    citations_payload.append(payload)

            yield {"type": "citations", "citations": citations_payload}

            text = cached["answer"] or ""
            if text:
                yield {"type": "token", "content": text}

            elapsed = int((time.perf_counter() - started) * 1000)
            response_row.time_ms = elapsed
            self._session.commit()
            yield {
                "type": "done",
                "status": response_row.status,
                "time_ms": elapsed,
            }
        except Exception:
            self._session.rollback()
            raise

    async def _finalize_insufficient(
        self,
        response_row: ResponseModel,
        started: float,
        skip_citations_event: bool = False,
    ) -> AsyncIterator[dict]:
        elapsed = int((time.perf_counter() - started) * 1000)
        response_row.response_text = ""
        response_row.status = ResponseStatus.INSUFFICIENT_INFORMATION.value
        response_row.time_ms = elapsed
        self._session.commit()
        if not skip_citations_event:
            yield {"type": "citations", "citations": []}
        yield {
            "type": "done",
            "status": response_row.status,
            "time_ms": elapsed,
        }

    def _build_and_persist_citations(
        self,
        raw_citations: list,
        contexts: list[dict],
        response_id: str,
    ) -> list[dict]:
        citations_payload: list[dict] = []
        seen_indices: set[int] = set()
        for c in raw_citations:
            if not isinstance(c, dict):
                continue
            context_index = c.get("context_index")
            if not isinstance(context_index, int):
                continue
            confidence = self._clamp_confidence(c.get("confidence"))
            if confidence is None or confidence < MIN_CITATION_CONFIDENCE:
                continue
            if context_index in seen_indices:
                continue
            payload = self._persist_citation_by_context(
                context_index, confidence, contexts, response_id
            )
            if payload is None:
                continue
            seen_indices.add(context_index)
            citations_payload.append(payload)
        return citations_payload

    async def ask_stream(
        self,
        question: str,
        chat_id: str | None = None,
        user_id: str | None = None,
        allowed_category_ids: list[str] | None = None,
    ) -> AsyncIterator[dict]:
        question = question.strip()
        if not question:
            raise ValidationError("Empty question.")

        started = time.perf_counter()

        # The Q&A cache is global; a cached answer may draw on categories the asker
        # cannot see. Only admins (unrestricted) read/write it — restricted users
        # always recompute against their own category scope.
        use_cache = allowed_category_ids is None

        question_embedding: list[float] | None = None
        cached = self._cache.lookup_exact(question) if use_cache else None
        if cached is None:
            embeds = await asyncio.to_thread(self._llm.embed, [question])
            question_embedding = embeds[0]
            if use_cache:
                cached = await asyncio.to_thread(
                    self._cache.lookup_semantic, question, question_embedding
                )
        if cached is not None and self._is_valid_cached_payload(cached):
            async for event in self._serve_cached_stream(
                question, cached, user_id, chat_id, started
            ):
                yield event
            return

        contexts = await asyncio.to_thread(
            self._vector_index.search,
            question,
            RAG_TOP_K,
            question_embedding,
            allowed_category_ids,
        )

        try:
            chat_id = self._resolve_or_create_chat(chat_id, question, user_id)

            query_row = Query(user_id=user_id, chat_id=chat_id, question=question)
            self._session.add(query_row)
            self._session.flush()

            response_row = ResponseModel(
                query_id=query_row.id,
                response_text="",
                status=ResponseStatus.SUCCESS.value,
                time_ms=0,
            )
            self._session.add(response_row)
            self._session.flush()

            yield {
                "type": "meta",
                "chat_id": chat_id,
                "query_id": query_row.id,
                "response_id": response_row.id,
            }

            if not contexts:
                async for event in self._finalize_insufficient(response_row, started):
                    yield event
                return

            history = self._load_chat_history(chat_id)
            rag_messages = build_messages(question, contexts)
            if history:
                rag_messages = [rag_messages[0], *history, rag_messages[1]]

            answer_parts: list[str] = []
            prev_answer = ""
            last_partial: dict | None = None
            citations_processed = False
            citations_emitted = False
            citations_payload: list[dict] = []

            def _to_partial_dict(obj: Any) -> dict:
                if isinstance(obj, dict):
                    return obj
                if hasattr(obj, "model_dump"):
                    return obj.model_dump()
                return {}

            try:
                async for partial in self._llm.chat_stream_structured(
                    rag_messages, RagAnswer
                ):
                    snapshot = _to_partial_dict(partial)
                    last_partial = snapshot

                    if not citations_processed and "answer" in snapshot:
                        raw_citations = snapshot.get("citations") or []
                        citations_payload = self._build_and_persist_citations(
                            raw_citations, contexts, response_row.id
                        )
                        citations_processed = True
                        if not citations_payload:
                            break
                        yield {"type": "citations", "citations": citations_payload}
                        citations_emitted = True

                    current_answer = snapshot.get("answer")
                    if not isinstance(current_answer, str):
                        continue
                    if len(current_answer) > len(prev_answer):
                        delta = current_answer[len(prev_answer):]
                        prev_answer = current_answer
                        answer_parts.append(delta)
                        yield {"type": "token", "content": delta}
            except LlmError as exc:
                elapsed = int((time.perf_counter() - started) * 1000)
                response_row.response_text = (
                    f"Error generating response ({exc.kind}): {exc.detail}"
                )
                response_row.status = ResponseStatus.ERROR.value
                response_row.time_ms = elapsed
                self._session.commit()
                logger.warning(
                    "stream %s LLM failed kind=%s detail=%s",
                    query_row.id,
                    exc.kind,
                    exc.detail,
                )
                yield {"type": "error", "kind": exc.kind, "message": exc.detail}
                return

            last_answer = "".join(answer_parts)

            if not citations_processed:
                raw_citations = (last_partial or {}).get("citations") or []
                citations_payload = self._build_and_persist_citations(
                    raw_citations, contexts, response_row.id
                )
                citations_processed = True

            if not last_answer and not citations_payload:
                async for event in self._finalize_insufficient(
                    response_row,
                    started,
                    skip_citations_event=citations_emitted,
                ):
                    yield event
                return

            response_row.response_text = last_answer
            response_row.status = ResponseStatus.SUCCESS.value
            elapsed = int((time.perf_counter() - started) * 1000)
            response_row.time_ms = elapsed
            self._session.commit()

            if not citations_emitted:
                yield {"type": "citations", "citations": citations_payload}
            yield {
                "type": "done",
                "status": response_row.status,
                "time_ms": elapsed,
            }

            if use_cache and question_embedding is not None:
                self._cache.put(
                    question,
                    question_embedding,
                    self._build_stream_cache_payload(
                        question, last_answer, citations_payload
                    ),
                )
        except Exception:
            self._session.rollback()
            raise

def get_chat_service(
    session: Session = Depends(get_session),
    vector_index: IVectorIndexService = Depends(get_vector_index_service),
    llm: LlmClient = Depends(get_llm_client),
    cache: IQaCache = Depends(get_qa_cache),
) -> IChatService:
    return ChatService(session, vector_index, llm, cache)
