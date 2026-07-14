from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.data.postgres_client import get_session, transaction
from src.enums.response_status import ResponseStatus
from src.exceptions import NotFoundError, ValidationError
from src.integrations.llm import LlmClient, LlmError, get_llm_client
from src.models.category import Category
from src.models.chat import Chat
from src.models.chat_folder import ChatFolder
from src.models.document_version import DocumentVersion
from src.models.evidence_citation import EvidenceCitation
from src.models.knowledge_document import KnowledgeDocument
from src.models.query import Query
from src.models.response import Response as ResponseModel
from src.prompts.condense_prompt import CondensedQuery, build_condense_messages
from src.prompts.rag_prompt import RagAnswer, build_messages
from src.protocols.qa_cache import QaCacheProtocol
from src.protocols.vector_index_service import VectorIndexServiceProtocol
from src.services.qa_cache import get_qa_cache
from src.services.vector_index_service import get_vector_index_service

logger = logging.getLogger(__name__)

CHAT_HISTORY_LIMIT = 10
CHAT_TITLE_MAX_CHARS = 60
RAG_TOP_K = 10
CONDENSE_MAX_TOKENS = 200

MIN_CITATION_CONFIDENCE = 0.6


class ChatService:
    def __init__(
        self,
        session: Session,
        vector_index: VectorIndexServiceProtocol,
        llm_client: LlmClient,
        cache: QaCacheProtocol,
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
            "category_id": chat.category_id,
            "created_at": chat.created_at.isoformat() if chat.created_at else None,
        }

    def _ensure_folder_owned(self, folder_id: str | None, user_id: str | None) -> None:
        if folder_id is None:
            return
        folder = self._session.get(ChatFolder, folder_id)
        if folder is None:
            raise NotFoundError(f"Chat folder not found: {folder_id}")
        if user_id is not None and folder.owner_id is not None and folder.owner_id != user_id:
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

    def list_chats(self, folder_id: str | None = None, user_id: str | None = None) -> list[dict]:
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
            .options(selectinload(Query.response).selectinload(ResponseModel.citations))
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
            doc_rows = (
                self._session.execute(
                    select(KnowledgeDocument)
                    .options(selectinload(KnowledgeDocument.versions))
                    .where(KnowledgeDocument.id.in_(document_ids))
                )
                .scalars()
                .all()
            )
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
                        response.created_at.isoformat() if response.created_at else None
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
        doc: KnowledgeDocument | None,
        version: DocumentVersion | None = None,
    ) -> dict:
        if version is None and doc is not None and citation.document_version_id is not None:
            version = doc.find_version_by_id(citation.document_version_id)
        return {
            "document_id": citation.document_id,
            "document_version_id": version.id if version else None,
            "version_number": version.version_number if version else None,
            "file_name": doc.file_name if doc else None,
            "page": citation.page,
            "excerpt": citation.used_excerpt,
            "confidence_score": citation.confidence_score,
            "download_url": (f"/documents/{citation.document_id}/download" if doc else None),
        }

    def update(self, chat_id: str, fields: dict, user_id: str | None = None) -> dict:
        with transaction(self._session):
            chat = self._load_owned(chat_id, user_id)
            if "folder_id" in fields:
                self._ensure_folder_owned(fields["folder_id"], user_id)
                chat.folder_id = fields["folder_id"]
            if "title" in fields and fields["title"] is not None:
                chat.title = fields["title"]
        self._session.refresh(chat)
        return self._serialize(chat)

    def delete(self, chat_id: str, user_id: str | None = None) -> None:
        with transaction(self._session):
            chat = self._load_owned(chat_id, user_id)
            self._session.delete(chat)

    def _resolve_version(
        self, document_id: str, version_number: int | None
    ) -> DocumentVersion | None:
        doc = self._session.get(KnowledgeDocument, document_id)
        if doc is None:
            return None
        return doc.find_version(version_number)

    def _serialize_citation(
        self,
        citation: EvidenceCitation,
        version: DocumentVersion | None = None,
    ) -> dict:
        doc = self._session.get(KnowledgeDocument, citation.document_id)
        return self._serialize_citation_with_doc(citation, doc, version)

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
        self,
        chat_id: str | None,
        question: str,
        user_id: str | None,
        category_id: str | None = None,
    ) -> str:
        if chat_id is not None:
            self._load_owned(chat_id, user_id)
            return chat_id
        chat = Chat(
            title=self._chat_title_from_question(question),
            user_id=user_id,
            category_id=category_id,
        )
        self._session.add(chat)
        self._session.flush()
        return chat.id

    def _resolve_scope_category(
        self, chat_id: str | None, category_id: str | None, user_id: str | None
    ) -> str | None:
        """Category id the retrieval must be limited to. An existing chat uses the
        category chosen when it was created; a new chat uses the requested one
        (validated here). ``None`` means search across every category."""
        if chat_id is not None:
            return self._load_owned(chat_id, user_id).category_id
        if category_id is not None and self._session.get(Category, category_id) is None:
            raise ValidationError(f"Unknown category: {category_id}")
        return category_id

    def _load_chat_history(self, chat_id: str) -> list[dict]:
        stmt = (
            select(Query)
            .where(Query.chat_id == chat_id)
            .options(selectinload(Query.response))
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
            history.append({"role": "assistant", "content": q.response.response_text})
        return history

    @staticmethod
    def _is_valid_cached_payload(payload: dict) -> bool:
        """Serve-side contract for cached payloads: grounded SUCCESS answers only,
        with every citation carrying the fields `_serve_cached_stream` replays.
        The shape check matters because L2 payloads are plain JSON persisted in
        Postgres — they outlive deploys and schema evolution."""
        if payload.get("status") != ResponseStatus.SUCCESS.value:
            return False
        answer = (payload.get("answer") or "").strip()
        if not answer:
            return False
        citations = payload.get("citations")
        if not isinstance(citations, list) or not citations:
            return False
        return all(
            isinstance(c, dict)
            and isinstance(c.get("document_id"), str)
            and isinstance(c.get("excerpt"), str)
            for c in citations
        )

    @staticmethod
    def _build_stream_cache_payload(question: str, answer: str, citations: list[dict]) -> dict:
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
        category_id: str | None = None,
    ) -> AsyncIterator[dict]:
        with transaction(self._session):
            chat_id = self._resolve_or_create_chat(chat_id, question, user_id, category_id)
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
                    version = self._resolve_version(c["document_id"], c.get("version_number"))
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

    async def _condense_question(self, history: list[dict], question: str) -> str:
        """Rewrite a follow-up into a self-contained retrieval query using the
        chat history, so questions like "e o segundo caso?" reach the embedding
        and the hybrid search with real semantic signal. Degrades gracefully:
        any failure or empty rewrite falls back to the raw question."""
        messages = build_condense_messages(history, question)
        last: dict = {}
        try:
            async for partial in self._llm.chat_stream_structured(
                messages, CondensedQuery, max_tokens=CONDENSE_MAX_TOKENS
            ):
                last = partial
        except LlmError as exc:
            logger.warning(
                "question condense failed (%s); searching with the raw question", exc.kind
            )
            return question
        rewritten = last.get("standalone_question")
        if isinstance(rewritten, str) and rewritten.strip():
            return rewritten.strip()
        return question

    def _persist_interrupted(
        self, response_row: ResponseModel, partial_answer: str, started: float
    ) -> None:
        """The client went away mid-stream (GeneratorExit/CancelledError): persist
        what was actually delivered so the turn doesn't silently vanish from the
        chat history. A partial answer is a truthful grounded prefix the user saw,
        so it keeps SUCCESS; with nothing delivered the placeholder stays ERROR."""
        response_id = response_row.id
        elapsed = int((time.perf_counter() - started) * 1000)
        try:
            with transaction(self._session):
                response_row.response_text = partial_answer
                if partial_answer:
                    response_row.status = ResponseStatus.SUCCESS.value
                response_row.time_ms = elapsed
        except Exception:
            logger.exception("failed to persist interrupted stream %s", response_id)

    async def ask_stream(
        self,
        question: str,
        chat_id: str | None = None,
        user_id: str | None = None,
        category_id: str | None = None,
    ) -> AsyncIterator[dict]:
        question = question.strip()
        if not question:
            raise ValidationError("Empty question.")

        started = time.perf_counter()

        scope_category_id = self._resolve_scope_category(chat_id, category_id, user_id)

        history: list[dict] = []
        search_question = question
        if chat_id is not None:
            history = self._load_chat_history(chat_id)
            if history:
                search_question = await self._condense_question(history, question)

        question_embedding: list[float] | None = None
        cached = self._cache.lookup_exact(search_question, scope_category_id)
        if cached is not None and not self._is_valid_cached_payload(cached):
            cached = None
        if cached is None:
            embeds = await asyncio.to_thread(self._llm.embed, [search_question])
            question_embedding = embeds[0]
            cached = await asyncio.to_thread(
                self._cache.lookup_semantic,
                search_question,
                question_embedding,
                scope_category_id,
            )
            if cached is not None and not self._is_valid_cached_payload(cached):
                cached = None
        if cached is not None:
            async for event in self._serve_cached_stream(
                question, cached, user_id, chat_id, started, scope_category_id
            ):
                yield event
            return

        cache_generation = self._cache.generation()
        contexts = await asyncio.to_thread(
            self._vector_index.search,
            search_question,
            RAG_TOP_K,
            question_embedding,
            scope_category_id,
        )

        with transaction(self._session):
            chat_id = self._resolve_or_create_chat(chat_id, question, user_id, scope_category_id)

            query_row = Query(user_id=user_id, chat_id=chat_id, question=question)
            self._session.add(query_row)
            self._session.flush()

            response_row = ResponseModel(
                query_id=query_row.id,
                response_text="",
                status=ResponseStatus.ERROR.value,
                time_ms=0,
            )
            self._session.add(response_row)
            self._session.flush()
        response_id = response_row.id

        yield {
            "type": "meta",
            "chat_id": chat_id,
            "query_id": query_row.id,
            "response_id": response_id,
        }

        if not contexts:
            async for event in self._finalize_insufficient(response_row, started):
                yield event
            return

        rag_messages = build_messages(question, contexts, history)

        answer_parts: list[str] = []
        prev_answer = ""
        last_partial: dict | None = None
        citations_processed = False
        citations_emitted = False
        citations_payload: list[dict] = []

        try:
            async for snapshot in self._llm.chat_stream_structured(rag_messages, RagAnswer):
                last_partial = snapshot

                if not citations_processed and "answer" in snapshot:
                    raw_citations = snapshot.get("citations") or []
                    with transaction(self._session):
                        citations_payload = self._build_and_persist_citations(
                            raw_citations, contexts, response_id
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
                    delta = current_answer[len(prev_answer) :]
                    prev_answer = current_answer
                    answer_parts.append(delta)
                    yield {"type": "token", "content": delta}
        except LlmError as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            with transaction(self._session):
                response_row.response_text = f"Error generating response ({exc.kind}): {exc.detail}"
                response_row.status = ResponseStatus.ERROR.value
                response_row.time_ms = elapsed
            logger.warning(
                "stream %s LLM failed kind=%s detail=%s",
                query_row.id,
                exc.kind,
                exc.detail,
            )
            yield {"type": "error", "kind": exc.kind, "message": exc.detail}
            return
        except BaseException:
            self._persist_interrupted(response_row, "".join(answer_parts), started)
            raise

        last_answer = "".join(answer_parts)

        if not citations_processed:
            raw_citations = (last_partial or {}).get("citations") or []
            with transaction(self._session):
                citations_payload = self._build_and_persist_citations(
                    raw_citations, contexts, response_id
                )
            citations_processed = True

        if not last_answer or not citations_payload:
            async for event in self._finalize_insufficient(
                response_row,
                started,
                skip_citations_event=citations_emitted,
            ):
                yield event
            return

        elapsed = int((time.perf_counter() - started) * 1000)
        with transaction(self._session):
            response_row.response_text = last_answer
            response_row.status = ResponseStatus.SUCCESS.value
            response_row.time_ms = elapsed

        if not citations_emitted:
            yield {"type": "citations", "citations": citations_payload}
        yield {
            "type": "done",
            "status": ResponseStatus.SUCCESS.value,
            "time_ms": elapsed,
        }

        if question_embedding is not None:
            payload = self._build_stream_cache_payload(
                search_question, last_answer, citations_payload
            )
            if self._is_valid_cached_payload(payload):
                self._cache.put(
                    search_question,
                    question_embedding,
                    payload,
                    scope_category_id,
                    generation=cache_generation,
                )


def get_chat_service(
    session: Session = Depends(get_session),
    vector_index: VectorIndexServiceProtocol = Depends(get_vector_index_service),
    llm: LlmClient = Depends(get_llm_client),
    cache: QaCacheProtocol = Depends(get_qa_cache),
) -> ChatService:
    return ChatService(session, vector_index, llm, cache)
