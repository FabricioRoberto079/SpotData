from src.prompts.condense_prompt import (
    CONDENSE_HISTORY_MESSAGES,
    CONDENSE_MESSAGE_MAX_CHARS,
    CONDENSE_SYSTEM_PROMPT,
    build_condense_messages,
)


def _exchange(i: int) -> list[dict]:
    return [
        {"role": "user", "content": f"pergunta {i}"},
        {"role": "assistant", "content": f"resposta {i}"},
    ]


def test_keeps_only_the_most_recent_history():
    history = [m for i in range(10) for m in _exchange(i)]
    messages = build_condense_messages(history, "e depois?")

    assert messages[0] == {"role": "system", "content": CONDENSE_SYSTEM_PROMPT}
    assert messages[-1] == {"role": "user", "content": "e depois?"}
    kept = messages[1:-1]
    assert len(kept) == CONDENSE_HISTORY_MESSAGES
    assert kept[0]["content"] == "pergunta 7"
    assert kept[-1]["content"] == "resposta 9"


def test_truncates_long_messages():
    history = [
        {"role": "user", "content": "pergunta"},
        {"role": "assistant", "content": "x" * (CONDENSE_MESSAGE_MAX_CHARS * 3)},
    ]
    messages = build_condense_messages(history, "e depois?")

    trimmed = messages[2]["content"]
    assert len(trimmed) == CONDENSE_MESSAGE_MAX_CHARS + 1
    assert trimmed.endswith("…")


def test_short_history_passes_through_unchanged():
    history = _exchange(0)
    messages = build_condense_messages(history, "e depois?")

    assert messages[1:-1] == history
