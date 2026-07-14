from pydantic import BaseModel, Field

from src.prompts.history import trim_history

CONDENSE_HISTORY_MESSAGES = 6
CONDENSE_MESSAGE_MAX_CHARS = 300

CONDENSE_SYSTEM_PROMPT = """\
You rewrite the user's latest message into one self-contained search query for \
a document retrieval system.

Rules:
- Resolve every pronoun and implicit reference ("it", "the second one", "and in \
practice?") using the conversation history.
- Keep the user's language and key terms; do not translate.
- Return a single question or search phrase, nothing else.
- If the message is already self-contained, return it unchanged.
- Never answer the question."""


class CondensedQuery(BaseModel):
    """Self-contained rewrite of the user's latest message, produced before
    retrieval so follow-up questions carry the semantic signal of the
    conversation instead of arriving as bare references."""

    standalone_question: str = Field(
        description=(
            "The user's latest message rewritten as one self-contained question "
            "or search phrase, in the same language, with every reference to the "
            "conversation resolved."
        )
    )


def build_condense_messages(history: list[dict], question: str) -> list[dict]:
    """Assemble the condense prompt from the tail of the history, truncating
    long messages: resolving a follow-up's references needs the recent topic,
    not full past answers, and the call's latency is dominated by input tokens."""
    return [
        {"role": "system", "content": CONDENSE_SYSTEM_PROMPT},
        *trim_history(history, CONDENSE_HISTORY_MESSAGES, CONDENSE_MESSAGE_MAX_CHARS),
        {"role": "user", "content": question},
    ]
