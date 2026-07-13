from datetime import UTC, datetime

from pydantic import BaseModel, Field

STALE_AFTER_DAYS = 365


class RegisterEvidence(BaseModel):
    """Register the source evidence that supports a factual claim by pointing
    at one of the CONTEXT entries. Use the integer in the `[index=N ...]`
    header of each entry — the server resolves document, version, page and
    excerpt from that index, so we keep the model's output tiny and fast."""

    context_index: int = Field(
        description=(
            "0-based index of the CONTEXT entry that supports this claim, "
            "exactly as shown in the entry's [index=N ...] header."
        )
    )
    confidence: float = Field(description="Confidence in this citation in the range 0.0–1.0.")


class RagAnswer(BaseModel):
    """The structured RAG answer. Plan `citations` from the CONTEXT first,
    then write `answer` so every claim is backed by one of those entries.

    Field order is load-bearing: strict JSON-schema decoding emits fields in
    schema order, and `chat_service.ask_stream` flushes the citations event
    as soon as `answer` first appears in the partial.
    """

    citations: list[RegisterEvidence] = Field(
        description=(
            "One entry per factual claim that will appear in `answer`. Empty "
            "when `answer` is empty or the question is conversational."
        )
    )
    answer: str = Field(
        description=(
            "The natural-language answer in Tiptap-compatible Markdown. "
            "MANDATORY: every substantive term from the user's question that "
            "appears here MUST be wrapped in `==…==` (Tiptap highlight, "
            "renders as <mark>). DO NOT substitute with `**bold**` — bold and "
            "highlight are distinct. Example: question 'O que é NTFS?' → "
            "answer must contain `==**NTFS**==`, never `**NTFS**` alone. "
            "Skip stopwords (qual, como, what, the, a, o, é, de). "
            "MUST NOT contain document IDs, source attributions, or citation-"
            "like JSON — those belong exclusively in the `citations` field. "
            "Leave empty only if CONTEXT does not cover the question or the "
            "user is greeting/chit-chatting."
        )
    )


SYSTEM_PROMPT = f"""You are an assistant that answers questions using STRICTLY \
the CONTEXT provided by the user.

You MUST output a single JSON object matching the schema with two top-level \
fields, IN THIS ORDER: `citations` and `answer`. First select the CONTEXT \
entries that back your answer and fill `citations` — one entry per claim, \
identifying each by its `context_index` (the integer in the `[index=N ...]` \
header). Then write `answer` so every substantive claim is backed by one of \
those citations. NEVER write document IDs, file names, source attributions, \
or quoted excerpts inside the `answer` string — sources belong EXCLUSIVELY \
in the `citations` array.

Rules:
- Use only information present in the CONTEXT. Do not invent anything.
- NO PARTIAL COVERAGE FROM GENERAL KNOWLEDGE. The mere presence of a name, term \
or entity in the CONTEXT does NOT authorize you to describe it from what you \
already know. Answer ONLY the specific facts literally stated in the CONTEXT \
snippets. If the CONTEXT merely mentions an entity but does not contain the \
facts the question asks for, treat the question as NOT covered: set `answer` to \
an empty string and leave `citations` empty. Example: if the CONTEXT names a \
person in passing but says nothing about their biography, do NOT supply their \
biography — return empty. Never blend retrieved snippets with outside knowledge.
- If the user is greeting, chit-chatting, thanking, saying goodbye, or otherwise \
NOT asking a question answerable from the CONTEXT (e.g. "oi", "olá", "tudo bem?", \
"obrigado", "hello", "how are you", "thanks"), set `answer` to an empty string \
and leave `citations` empty.
- If the CONTEXT does not cover the question, set `answer` to an empty string \
and leave `citations` empty.
- When `answer` is non-empty, every substantive claim in it MUST be backed by \
at least one matching entry in `citations`. Each citation must reference a \
real `context_index` from the CONTEXT block; never invent indices.
- Answer in the same language as the question.
- Each context entry includes the version's `created_at` date. When cited \
content is older than {STALE_AFTER_DAYS} days relative to TODAY, append a short \
warning at the end of `answer` mentioning the document date.
- Format `answer` as Tiptap-compatible Markdown: **bold** (for emphasis on \
non-question terms only), *italic*, `code`, lists (- / 1.), headings (##), \
tables. Do not wrap the whole answer in code blocks.
- MANDATORY HIGHLIGHTING — every substantive term from the QUESTION that \
appears in `answer` MUST be wrapped in `==…==` (Tiptap highlight syntax, \
rendered as `<mark>`). This is NOT optional and `**bold**` is NOT a \
substitute — they are distinct marks. Skip only stopwords (qual, como, \
quanto, what, the, a, o, é, de). Highlight on the FIRST occurrence of each \
distinct term; further mentions are optional. To emphasize a highlighted \
term, NEST: `==**term**==` (not `**term**` alone).

Concrete examples (note `==…==`, never `**bold**` alone for question terms):

  QUESTION: "Qual a meta de receita de 2026 e a divisão entre canais?"
  ✓ GOOD: "A ==meta de receita== para ==2026== é de **BRL 12 milhões**. \
A ==divisão entre canais== é **60%** varejo e **40%** atacado."
  ✗ BAD (bold instead of highlight): "A **meta de receita** para **2026** é..."
  ✗ BAD (highlighted stopword): "==Qual== a ==meta== ..."

  QUESTION: "O que é o sistema de arquivos NTFS?"
  ✓ GOOD: "O ==**sistema de arquivos NTFS**== é um sistema desenvolvido para…"
  ✗ BAD: "O **sistema de arquivos NTFS** é um sistema desenvolvido para…" """


def _format_created_at(value) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)


def _build_user_content(question: str, contexts: list[dict]) -> str:
    today = datetime.now(UTC).date().isoformat()
    if contexts:
        context_block = "\n\n".join(
            f"[index={i} file={c.get('file_name')} "
            f"created_at={_format_created_at(c.get('version_created_at'))}]\n"
            f"{c.get('snippet', '')}"
            for i, c in enumerate(contexts)
        )
    else:
        context_block = "(empty)"
    return f"TODAY: {today}\n\nCONTEXT:\n{context_block}\n\nQUESTION: {question}"


def build_messages(
    question: str, contexts: list[dict], history: list[dict] | None = None
) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *(history or []),
        {"role": "user", "content": _build_user_content(question, contexts)},
    ]
