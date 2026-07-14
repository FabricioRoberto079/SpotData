def _trim_message(message: dict, max_chars: int) -> dict:
    content = message.get("content") or ""
    if len(content) <= max_chars:
        return message
    return {**message, "content": content[:max_chars].rstrip() + "…"}


def trim_history(history: list[dict], max_messages: int, max_chars: int) -> list[dict]:
    """Bound conversation history for prompt building: keep only the most recent
    ``max_messages`` entries and truncate each message body to ``max_chars``.
    Prompt latency and cost are dominated by input tokens, so every consumer of
    chat history states its budget explicitly through this single helper."""
    return [_trim_message(m, max_chars) for m in history[-max_messages:]]
