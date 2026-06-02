from abc import ABC, abstractmethod


class IEmailSender(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None: ...
