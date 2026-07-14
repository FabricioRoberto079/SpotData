from typing import Protocol


class VectorIndexServiceProtocol(Protocol):
    def prepare(self, text: str) -> tuple[list[str], list[list[float]]]: ...
    def prepare_paged(self, pages: list[str]) -> tuple[list[str], list[list[float]], list[int]]: ...
    def commit(
        self,
        document_id: str,
        version_number: int,
        file_name: str,
        content_type: str,
        chunks: list[str],
        embeddings: list[list[float]],
        pages_per_chunk: list[int] | None = None,
        category_id: str | None = None,
    ) -> int: ...
    def demote_latest(self, document_id: str) -> None: ...
    def purge_document(self, document_id: str) -> None: ...
    def search(
        self,
        query: str,
        n_results: int = 5,
        embedding: list[float] | None = None,
        category_id: str | None = None,
    ) -> list[dict]: ...
