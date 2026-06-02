from abc import ABC, abstractmethod


class IVectorIndexService(ABC):
    @abstractmethod
    def prepare(self, text: str) -> tuple[list[str], list[list[float]]]: ...

    @abstractmethod
    def prepare_paged(
        self, pages: list[str]
    ) -> tuple[list[str], list[list[float]], list[int]]: ...

    @abstractmethod
    def commit(
        self,
        document_id: str,
        version_number: int,
        file_name: str,
        content_type: str,
        chunks: list[str],
        embeddings: list[list[float]],
        pages_per_chunk: list[int | None] | None = None,
        category_id: str | None = None,
    ) -> int: ...

    @abstractmethod
    def demote_latest(self, document_id: str) -> None: ...

    @abstractmethod
    def purge_document(self, document_id: str) -> None: ...

    @abstractmethod
    def search(
        self,
        query: str,
        n_results: int = 5,
        embedding: list[float] | None = None,
        allowed_category_ids: list[str] | None = None,
    ) -> list[dict]: ...
