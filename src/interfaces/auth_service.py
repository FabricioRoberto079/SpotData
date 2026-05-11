from abc import ABC, abstractmethod


class IAuthService(ABC):
    @abstractmethod
    def register(
        self, name: str, email: str, password: str, role: str = "user"
    ) -> dict: ...

    @abstractmethod
    def login(self, email: str, password: str) -> dict: ...
