from abc import ABC, abstractmethod


class IFolderService(ABC):
    @abstractmethod
    def create(
        self,
        name: str,
        parent_id: str | None = None,
        owner_id: str | None = None,
    ) -> dict: ...

    @abstractmethod
    def list_tree(self, owner_id: str | None = None) -> list[dict]: ...

    @abstractmethod
    def update(self, folder_id: str, fields: dict, owner_id: str | None = None) -> dict: ...

    @abstractmethod
    def delete(self, folder_id: str, owner_id: str | None = None) -> None: ...
