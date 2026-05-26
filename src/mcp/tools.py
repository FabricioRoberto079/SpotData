import logging

from mcp.server.fastmcp import Context

from src.data.postgres_client import SessionLocal
from src.integrations.llm import get_llm_client
from src.mcp.auth import resolve_user_id_from_token
from src.mcp.server import mcp_server
from src.services.chat_service import ChatService
from src.services.qa_cache import get_qa_cache
from src.services.text_chunker import get_text_chunker
from src.services.vector_index_service import VectorIndexService

logger = logging.getLogger(__name__)


def _extract_bearer(ctx: Context) -> str:
    """Pull the Bearer token from the HTTP Authorization header of the active MCP request.

    The MCP server can run over stdio or HTTP transports; for the HTTP transport
    FastMCP exposes the underlying Starlette request through the request context.
    """
    request = getattr(ctx.request_context, "request", None)
    if request is None:
        raise RuntimeError(
            "MCP tool requires HTTP transport with a Bearer token; no request available."
        )
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise RuntimeError("Authorization header missing or malformed.")
    token = auth_header[7:].strip()
    if not token:
        raise RuntimeError("Empty token.")
    return token


async def _ask(question: str, chat_id: str | None, user_id: str) -> dict:
    session = SessionLocal()
    try:
        llm = get_llm_client()
        chunker = get_text_chunker()
        vector_index = VectorIndexService(session, chunker, llm)
        cache = get_qa_cache()
        chat_service = ChatService(session, vector_index, llm, cache)

        meta: dict = {}
        citations: list[dict] = []
        answer_parts: list[str] = []
        done: dict = {}
        error: dict | None = None

        async for event in chat_service.ask_stream(
            question=question,
            chat_id=chat_id,
            user_id=user_id,
        ):
            kind = event.get("type")
            if kind == "meta":
                meta = event
            elif kind == "citation":
                citations.append(event["citation"])
            elif kind == "token":
                answer_parts.append(event.get("content", ""))
            elif kind == "done":
                done = event
            elif kind == "error":
                error = event

        if error is not None:
            return {
                "chat_id": meta.get("chat_id"),
                "query_id": meta.get("query_id"),
                "response_id": meta.get("response_id"),
                "question": question,
                "status": "error",
                "kind": error.get("kind"),
                "message": error.get("message"),
            }

        return {
            "chat_id": meta.get("chat_id"),
            "query_id": meta.get("query_id"),
            "response_id": meta.get("response_id"),
            "question": question,
            "status": done.get("status"),
            "answer": "".join(answer_parts),
            "citations": citations,
            "time_ms": done.get("time_ms"),
        }
    finally:
        session.close()


@mcp_server.tool()
async def ask_question(
    ctx: Context,
    question: str,
    chat_id: str | None = None,
) -> dict:
    """Ask a question against the SpotData knowledge base (RAG).

    Runs semantic search over the latest indexed chunks, calls the LLM with the
    retrieved context, and returns an answer grounded in the documents — or
    `insufficient_information` when the corpus does not cover the question.

    Auth: requires an `Authorization: Bearer <JWT>` header on the MCP HTTP request.
    The user_id is taken from the token; never from server env vars.

    Args:
        question: Natural-language question (1-4000 chars).
        chat_id: Optional existing chat to thread the message into. If omitted,
            a new chat is created and its id is returned in the response.

    Returns:
        A dict with `chat_id`, `query_id`, `response_id`, `question`, `status`
        (`success` | `insufficient_information` | `error`), `answer`,
        `citations`, and `time_ms`. When `status='insufficient_information'`,
        `answer` is an empty string and `citations` is an empty list.
    """
    token = _extract_bearer(ctx)
    user_id = resolve_user_id_from_token(token)
    return await _ask(question, chat_id, user_id)
