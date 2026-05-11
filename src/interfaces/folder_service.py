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
    def rename(self, folder_id: str, name: str) -> dict: ...

    @abstractmethod
    def move(self, folder_id: str, new_parent_id: str | None) -> dict: ...

    @abstractmethod
    def delete(self, folder_id: str) -> None: ...
