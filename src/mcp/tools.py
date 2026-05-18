import asyncio

from src.data.postgres_client import SessionLocal
from src.integrations.llm import get_llm_client
from src.mcp.auth import resolve_user_id
from src.mcp.server import mcp_server
from src.services.chat_service import ChatService
from src.services.text_chunker import get_text_chunker
from src.services.vector_index_service import VectorIndexService


def _ask_sync(question: str, chat_id: str | None, n_results: int) -> dict:
    user_id = resolve_user_id()
    session = SessionLocal()
    try:
        llm = get_llm_client()
        chunker = get_text_chunker()
        vector_index = VectorIndexService(session, chunker, llm)
        chat_service = ChatService(session, vector_index, llm)
        return chat_service.ask(
            question=question,
            chat_id=chat_id,
            user_id=user_id,
            n_results=n_results,
        )
    finally:
        session.close()


@mcp_server.tool()
async def ask_question(
    question: str,
    chat_id: str | None = None,
    n_results: int = 5,
) -> dict:
    """Ask a question against the SpotData knowledge base (RAG).

    Runs semantic search over the latest indexed chunks, calls the configured
    LLM with the retrieved context, and returns the answer plus citations.

    Args:
        question: Natural-language question (1-4000 chars).
        chat_id: Optional existing chat to thread the message into. If omitted,
            a new chat is created and its id is returned in the response.
        n_results: How many top chunks to retrieve as context (1-20).

    Returns:
        A dict with `query_id`, `chat_id`, `question`, `status`
        (`success` | `insufficient_information` | `not_found` | `error`),
        `answer`, `citations`, and `time_ms`.
    """
    return await asyncio.to_thread(_ask_sync, question, chat_id, n_results)
