from src.enums.upload_kind import UploadKind
from src.protocols.upload_strategy import UploadPayload, UploadStrategyProtocol
from src.services.upload_strategies.file import FileUploadStrategy
from src.services.upload_strategies.image import ImageUploadStrategy
from src.services.upload_strategies.text import TextUploadStrategy

_REGISTRY: dict[UploadKind, UploadStrategyProtocol] = {
    UploadKind.FILE: FileUploadStrategy(),
    UploadKind.IMAGE: ImageUploadStrategy(),
    UploadKind.TEXT: TextUploadStrategy(),
}


def get_upload_strategy(kind: UploadKind) -> UploadStrategyProtocol:
    return _REGISTRY[kind]


__all__ = [
    "FileUploadStrategy",
    "UploadStrategyProtocol",
    "ImageUploadStrategy",
    "TextUploadStrategy",
    "UploadPayload",
    "get_upload_strategy",
]
