from __future__ import annotations

import logging
import time

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.data.postgres_client import get_session
from src.enums.response_status import ResponseStatus
from src.exceptions import NotFoundError, ValidationError
from src.integrations.llm import LlmClient, LlmError, get_llm_client
from src.interfaces.chat_service import IChatService
from src.interfaces.qa_cache import IQaCache
from src.interfaces.vector_index_service import IVectorIndexService
from src.models.chat import Chat
from src.models.chat_folder import ChatFolder
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
RAG_TOP_K = 5


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

    def _ensure_folder_exists(self, folder_id: str | None) -> None:
        if folder_id is None:
            return
        if self._session.get(ChatFolder, folder_id) is None:
            raise NotFoundError(f"Chat folder not found: {folder_id}")

    def list(self, folder_id: str | None = None) -> list[dict]:
        stmt = select(Chat)
        if folder_id is not None:
            stmt = stmt.where(Chat.folder_id == folder_id)
        items = self._session.execute(stmt).scalars().all()
        return [self._serialize(c) for c in items]

    def get(self, chat_id: str) -> dict:
        chat = self._session.get(Chat, chat_id)
        if chat is None:
            raise NotFoundError(f"Chat not found: {chat_id}")
        return self._serialize(chat)

    def update(self, chat_id: str, fields: dict) -> dict:
        try:
            chat = self._session.get(Chat, chat_id)
            if chat is None:
                raise NotFoundError(f"Chat not found: {chat_id}")
            if "folder_id" in fields:
                self._ensure_folder_exists(fields["folder_id"])
                chat.folder_id = fields["folder_id"]
            if "title" in fields and fields["title"] is not None:
                chat.title = fields["title"]
            self._session.commit()
            self._session.refresh(chat)
            return self._serialize(chat)
        except Exception:
            self._session.rollback()
            raise

    def delete(self, chat_id: str) -> None:
        try:
            chat = self._session.get(Chat, chat_id)
            if chat is None:
                raise NotFoundError(f"Chat not found: {chat_id}")
            self._session.delete(chat)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def _latest_version_id(self, document_id: str) -> str | None:
        doc = self._session.get(KnowledgeDocument, document_id)
        if doc is None or not doc.versions:
            return None
        latest = max(doc.versions, key=lambda v: v.version_number)
        return latest.id

    def _serialize_citation(self, citation: EvidenceCitation) -> dict:
        doc = self._session.get(KnowledgeDocument, citation.document_id)
        latest = (
            max(doc.versions, key=lambda v: v.version_number)
            if doc and doc.versions
            else None
        )
        return {
            "document_id": citation.document_id,
            "document_version_id": latest.id if latest else None,
            "version_number": latest.version_number if latest else None,
            "file_name": doc.file_name if doc else None,
            "excerpt": citation.used_excerpt,
            "confidence_score": citation.confidence_score,
            "download_url": (
                f"/documents/{citation.document_id}/download" if doc else None
            ),
        }

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
            if self._session.get(Chat, chat_id) is None:
                raise NotFoundError(f"Chat not found: {chat_id}")
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

        history = []
        for q in queries:
            history.append({"role": "user", "content": q.question})
            if q.response is not None:
                history.append(
                    {"role": "assistant", "content": q.response.response_text}
                )
        return history

    def _persist_response(
        self,
        query_id: str,
        text: str,
        status: str,
        elapsed_ms: int,
    ) -> ResponseModel:
        response_row = ResponseModel(
            query_id=query_id,
            response_text=text,
            status=status,
            time_ms=elapsed_ms,
        )
        self._session.add(response_row)
        self._session.flush()
        return response_row

    def _build_cache_payload(self, question: str, rag: RagAnswer) -> dict:
        return {
            "question": question,
            "answer": rag.answer,
            "status": rag.status,
            "citations": [
                {
                    "document_id": c.document_id,
                    "version_number": c.version_number,
                    "excerpt": c.excerpt,
                    "confidence_score": c.confidence_score,
                }
                for c in rag.citations
            ],
        }

    def _serve_from_cache(
        self,
        question: str,
        cached: dict,
        user_id: str | None,
        started: float,
    ) -> dict:
        try:
            chat_id = self._resolve_or_create_chat(None, question, user_id)
            query_row = Query(user_id=user_id, chat_id=chat_id, question=question)
            self._session.add(query_row)
            self._session.flush()

            elapsed = int((time.perf_counter() - started) * 1000)
            response_row = self._persist_response(
                query_row.id,
                cached["answer"],
                cached["status"],
                elapsed,
            )

            citations_payload: list[dict] = []
            if cached["status"] == ResponseStatus.SUCCESS.value:
                for c in cached.get("citations", []):
                    doc = self._session.get(KnowledgeDocument, c["document_id"])
                    if doc is None:
                        continue
                    version_id = self._latest_version_id(c["document_id"])
                    citation_row = EvidenceCitation(
                        response_id=response_row.id,
                        document_id=c["document_id"],
                        document_version_id=version_id,
                        used_excerpt=c["excerpt"],
                        confidence_score=c["confidence_score"],
                    )
                    self._session.add(citation_row)
                    self._session.flush()
                    citations_payload.append(self._serialize_citation(citation_row))

            self._session.commit()
            logger.info(
                "message %s cached=true status=%s citations=%d elapsed=%dms",
                query_row.id,
                response_row.status,
                len(citations_payload),
                elapsed,
            )
            return {
                "query_id": query_row.id,
                "response_id": response_row.id,
                "chat_id": chat_id,
                "question": question,
                "status": response_row.status,
                "answer": response_row.response_text,
                "citations": citations_payload,
                "time_ms": elapsed,
            }
        except Exception:
            self._session.rollback()
            raise

    def ask(
        self,
        question: str,
        chat_id: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        question = question.strip()
        if not question:
            raise ValidationError("Empty question.")

        started = time.perf_counter()
        cache_eligible = chat_id is None

        if cache_eligible:
            cached = self._cache.lookup_exact(question)
            if cached is not None:
                return self._serve_from_cache(question, cached, user_id, started)

        question_embedding: list[float] | None = None
        if cache_eligible:
            question_embedding = self._llm.embed([question])[0]
            cached = self._cache.lookup_semantic(question, question_embedding)
            if cached is not None:
                return self._serve_from_cache(question, cached, user_id, started)

        contexts = self._vector_index.search(
            question, n_results=RAG_TOP_K, embedding=question_embedding
        )

        try:
            chat_id = self._resolve_or_create_chat(chat_id, question, user_id)

            query_row = Query(user_id=user_id, chat_id=chat_id, question=question)
            self._session.add(query_row)
            self._session.flush()

            if not contexts:
                elapsed = int((time.perf_counter() - started) * 1000)
                response_row = self._persist_response(
                    query_row.id,
                    "No related documents were found in the collection.",
                    ResponseStatus.NOT_FOUND.value,
                    elapsed,
                )
                self._session.commit()
                logger.info(
                    "message %s status=%s elapsed=%dms",
                    query_row.id,
                    response_row.status,
                    elapsed,
                )
                return {
                    "query_id": query_row.id,
                    "response_id": response_row.id,
                    "chat_id": chat_id,
                    "question": question,
                    "status": response_row.status,
                    "answer": response_row.response_text,
                    "citations": [],
                    "time_ms": elapsed,
                }

            history = self._load_chat_history(chat_id)
            rag_messages = build_messages(question, contexts)
            if history:
                rag_messages = [rag_messages[0], *history, rag_messages[1]]

            try:
                rag: RagAnswer = self._llm.chat_structured(rag_messages, RagAnswer)
            except LlmError as exc:
                elapsed = int((time.perf_counter() - started) * 1000)
                self._persist_response(
                    query_row.id,
                    f"Error generating response ({exc.kind}): {exc.detail}",
                    ResponseStatus.ERROR.value,
                    elapsed,
                )
                self._session.commit()
                logger.warning(
                    "message %s LLM falhou kind=%s detail=%s",
                    query_row.id,
                    exc.kind,
                    exc.detail,
                )
                raise
            except Exception as exc:
                elapsed = int((time.perf_counter() - started) * 1000)
                self._persist_response(
                    query_row.id,
                    f"Unexpected error generating response: {exc}",
                    ResponseStatus.ERROR.value,
                    elapsed,
                )
                self._session.commit()
                logger.exception("message %s falhou no LLM", query_row.id)
                raise

            elapsed = int((time.perf_counter() - started) * 1000)
            response_row = self._persist_response(
                query_row.id, rag.answer, rag.status, elapsed
            )

            citations_payload = []
            if rag.status == ResponseStatus.SUCCESS.value:
                for c in rag.citations:
                    doc = self._session.get(KnowledgeDocument, c.document_id)
                    if doc is None:
                        continue
                    version_id = self._latest_version_id(c.document_id)
                    citation_row = EvidenceCitation(
                        response_id=response_row.id,
                        document_id=c.document_id,
                        document_version_id=version_id,
                        used_excerpt=c.excerpt,
                        confidence_score=c.confidence_score,
                    )
                    self._session.add(citation_row)
                    self._session.flush()
                    citations_payload.append(self._serialize_citation(citation_row))

            self._session.commit()
            logger.info(
                "message %s status=%s citations=%d elapsed=%dms",
                query_row.id,
                response_row.status,
                len(citations_payload),
                elapsed,
            )

            if (
                cache_eligible
                and question_embedding is not None
                and rag.status == ResponseStatus.SUCCESS.value
            ):
                self._cache.put(
                    question,
                    question_embedding,
                    self._build_cache_payload(question, rag),
                )

            return {
                "query_id": query_row.id,
                "response_id": response_row.id,
                "chat_id": chat_id,
                "question": question,
                "status": response_row.status,
                "answer": response_row.response_text,
                "citations": citations_payload,
                "time_ms": elapsed,
            }
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
