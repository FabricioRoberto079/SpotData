from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


LlmStatus = Literal["success", "insufficient_information"]

STALE_AFTER_DAYS = 365


class Citation(BaseModel):
    document_id: str = Field(description="ID of the cited KnowledgeDocument.")
    version_number: int | None = Field(
        default=None, description="Version number consulted (when known)."
    )
    excerpt: str = Field(description="Literal excerpt taken from the document.")
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Confidence from 0.0 to 1.0 about the citation."
    )


class RagAnswer(BaseModel):
    status: LlmStatus = Field(
        description=(
            "'success' if the answer was produced from the context, "
            "'insufficient_information' if the context does not cover the question."
        )
    )
    answer: str = Field(description="Natural-language answer.")
    citations: list[Citation] = Field(
        default_factory=list,
        description="Citations supporting the answer. Empty when status != success.",
    )


SYSTEM_PROMPT = f"""You are an assistant that answers questions using \
strictly the CONTEXT provided by the user.

Mandatory rules:
1. Use only information present in the CONTEXT. Do not invent anything.
2. If the CONTEXT does not cover the question, return status='insufficient_information' \
and leave `citations` empty.
3. Each relevant statement must have at least one citation pointing to the \
document (document_id) with a literal excerpt and a realistic confidence_score.
4. The answer must be objective and written in the same language as the question.
5. Each context entry includes the version's `created_at` date. When the cited \
content is older than {STALE_AFTER_DAYS} days relative to TODAY, append a short \
warning at the end of `answer` in the same language as the question, mentioning \
the document date (e.g. "based on a document from 2024-02 — verify if still current").
6. Format `answer` as Markdown compatible with Tiptap: use **bold**, *italic*, \
`code`, lists (- / 1.), headings (##) and tables when they help readability. \
Do not wrap the whole answer in code blocks.
7. MANDATORY HIGHLIGHTING — every substantive term from the QUESTION that appears \
in `answer` MUST be wrapped in `==…==` (Tiptap highlight syntax, rendered as `<mark>`). \
This is NOT optional. Skip only stopwords (qual, como, quanto, what, the, a, o, é, de). \
Highlight on the FIRST occurrence of each distinct term; further mentions are optional. \
You can combine with **bold** by nesting: `==**term**==`. Excerpts inside `citations` \
MUST remain literal — never add `==` or any other markup there.

Concrete example (note how every substantive term from the question is wrapped in ==…==):
  QUESTION: "Qual a meta de receita de 2026 e a divisão entre canais?"
  GOOD answer: "A ==meta de receita== para ==2026== é de **BRL 12 milhões**. \
A ==divisão entre canais== é **60%** varejo e **40%** atacado."
  BAD answer (missing highlights): "A meta de receita para 2026 é de BRL 12 milhões..."
  BAD answer (highlighted stopwords): "==Qual== a ==meta== ..." """


def _format_created_at(value) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)


def build_messages(question: str, contexts: list[dict]) -> list[dict]:
    today = datetime.now(timezone.utc).date().isoformat()
    if contexts:
        context_block = "\n\n".join(
            f"[document_id={c.get('document_id')} version={c.get('version_number')} "
            f"file={c.get('file_name')} "
            f"created_at={_format_created_at(c.get('version_created_at'))}]\n"
            f"{c.get('snippet', '')}"
            for c in contexts
        )
    else:
        context_block = "(empty)"

    user_content = (
        f"TODAY: {today}\n\n"
        f"CONTEXT:\n{context_block}\n\n"
        f"QUESTION: {question}"
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
