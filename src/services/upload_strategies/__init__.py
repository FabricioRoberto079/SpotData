from src.enums.upload_kind import UploadKind
from src.interfaces.upload_strategy import IUploadStrategy, UploadPayload
from src.services.upload_strategies.file import FileUploadStrategy
from src.services.upload_strategies.image import ImageUploadStrategy
from src.services.upload_strategies.text import TextUploadStrategy

_REGISTRY: dict[UploadKind, IUploadStrategy] = {
    UploadKind.FILE: FileUploadStrategy(),
    UploadKind.IMAGE: ImageUploadStrategy(),
    UploadKind.TEXT: TextUploadStrategy(),
}


def get_upload_strategy(kind: UploadKind) -> IUploadStrategy:
    return _REGISTRY[kind]


__all__ = [
    "FileUploadStrategy",
    "IUploadStrategy",
    "ImageUploadStrategy",
    "TextUploadStrategy",
    "UploadPayload",
    "get_upload_strategy",
]
