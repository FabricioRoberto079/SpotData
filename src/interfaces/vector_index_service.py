from abc import ABC, abstractmethod


class IVectorIndexService(ABC):
    @abstractmethod
    def index_text(
        self,
        document_id: str,
        version_number: int,
        file_name: str,
        content_type: str,
        text: str,
    ) -> int: ...

    @abstractmethod
    def demote_latest(self, document_id: str) -> None: ...

    @abstractmethod
    def purge_document(self, document_id: str) -> None: ...

    @abstractmethod
    def search(self, query: str, n_results: int = 5) -> list[dict]: ...
