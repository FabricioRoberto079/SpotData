from enum import StrEnum


class ContentType(StrEnum):
    """Stored content formats.

    The values ("texto", "foto") are the legacy wire/DB representation —
    they are persisted in `vector_chunks.content_type` and exposed by the
    API, so renaming a member must never change its value.
    """

    TEXT = "texto"
    PDF = "pdf"
    IMAGE = "foto"
    DOC = "doc"
