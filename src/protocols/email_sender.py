from typing import Protocol


class EmailSenderProtocol(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...
