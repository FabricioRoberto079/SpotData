from abc import ABC, abstractmethod


class IAuthService(ABC):
    @abstractmethod
    def register(self, name: str, email: str, password: str) -> dict: ...

    @abstractmethod
    def login(self, email: str, password: str) -> dict: ...

    @abstractmethod
    def request_password_reset(self, email: str) -> None: ...

    @abstractmethod
    def reset_password(self, email: str, code: str, new_password: str) -> None: ...
