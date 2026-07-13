from fastapi import UploadFile

from src.enums.content_type import ContentType
from src.enums.document_category import DocumentCategory
from src.exceptions import ValidationError
from src.interfaces.upload_strategy import IUploadStrategy, UploadPayload
from src.services.upload_strategies._shared import MAX_UPLOAD_SIZE, clean_optional


class TextUploadStrategy(IUploadStrategy):
    async def build_payload(
        self,
        *,
        file: UploadFile | None,
        text: str | None,
        file_name: str | None,
    ) -> UploadPayload:
        if text is None or not text.strip():
            raise ValidationError("Missing or empty 'text' for text upload.")
        encoded = text.strip().encode("utf-8")
        if len(encoded) > MAX_UPLOAD_SIZE:
            raise ValidationError(f"Text exceeds {MAX_UPLOAD_SIZE // (1024 * 1024)}MB limit.")
        name = clean_optional(file_name) or "plain-text"
        return UploadPayload(
            file_data=encoded,
            content_type=ContentType.TEXT,
            file_name=name,
            category=DocumentCategory.TEXT,
        )
