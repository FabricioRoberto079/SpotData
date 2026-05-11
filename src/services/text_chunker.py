from __future__ import annotations

import re

from src.interfaces.text_chunker import ITextChunker

DEFAULT_MAX_CHARS = 1500
DEFAULT_OVERLAP = 200
MIN_CHUNK_CHARS = 50

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class TextChunker(ITextChunker):
    def __init__(
        self,
        max_chars: int = DEFAULT_MAX_CHARS,
        overlap: int = DEFAULT_OVERLAP,
    ) -> None:
        self._default_max_chars = max_chars
        self._default_overlap = overlap

    @staticmethod
    def _split_long_block(block: str, max_chars: int) -> list[str]:
        if len(block) <= max_chars:
            return [block]

        sentences = _SENTENCE_SPLIT.split(block)
        pieces: list[str] = []
        current = ""
        for sentence in sentences:
            if not sentence.strip():
                continue
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                pieces.append(current)
            if len(sentence) <= max_chars:
                current = sentence
            else:
                for i in range(0, len(sentence), max_chars):
                    pieces.append(sentence[i : i + max_chars])
                current = ""
        if current:
            pieces.append(current)
        return pieces

    @staticmethod
    def _tail_overlap(text: str, overlap: int) -> str:
        if overlap <= 0 or len(text) <= overlap:
            return text
        snippet = text[-overlap:]
        space = snippet.find(" ")
        return snippet[space + 1 :] if space != -1 else snippet

    def chunk(
        self,
        text: str,
        max_chars: int | None = None,
        overlap: int | None = None,
    ) -> list[str]:
        max_chars = max_chars if max_chars is not None else self._default_max_chars
        overlap = overlap if overlap is not None else self._default_overlap

        text = (text or "").strip()
        if not text:
            return []
        if len(text) <= max_chars:
            return [text]

        paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]
        if not paragraphs:
            paragraphs = [text]

        blocks: list[str] = []
        for paragraph in paragraphs:
            blocks.extend(self._split_long_block(paragraph, max_chars))

        chunks: list[str] = []
        current = ""
        for block in blocks:
            if not current:
                current = block
                continue
            candidate_len = len(current) + 2 + len(block)
            if candidate_len <= max_chars:
                current = f"{current}\n\n{block}"
                continue
            chunks.append(current)
            prefix = self._tail_overlap(current, overlap)
            current = f"{prefix}\n\n{block}" if prefix else block
            if len(current) > max_chars:
                chunks.append(current[:max_chars])
                current = current[max_chars - overlap :] if overlap else ""
        if current:
            chunks.append(current)

        return [c for c in chunks if len(c) >= MIN_CHUNK_CHARS] or chunks


def get_text_chunker() -> ITextChunker:
    return TextChunker()
