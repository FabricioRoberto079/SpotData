from fastapi import UploadFile

from src.enums.content_type import ContentType
from src.enums.document_category import DocumentCategory
from src.exceptions import ValidationError
from src.interfaces.upload_strategy import IUploadStrategy, UploadPayload
from src.services.upload_strategies._shared import (
    IMAGE_EXTENSIONS,
    clean_optional,
    extract_ext,
    read_upload,
    validate_mime_for_ext,
)


class ImageUploadStrategy(IUploadStrategy):
    async def build_payload(
        self,
        *,
        file: UploadFile | None,
        text: str | None,
        file_name: str | None,
    ) -> UploadPayload:
        if file is None:
            raise ValidationError("Missing 'file' for image upload.")
        filename = file.filename or ""
        ext = extract_ext(filename)
        if ext not in IMAGE_EXTENSIONS:
            raise ValidationError(
                f"Unsupported image extension '{ext}'. "
                f"Accepted: {', '.join(sorted(IMAGE_EXTENSIONS))}."
            )
        data = await read_upload(file)
        validate_mime_for_ext(ext, data)
        name = clean_optional(file_name) or filename
        return UploadPayload(
            file_data=data,
            content_type=ContentType.FOTO,
            file_name=name,
            category=DocumentCategory.IMAGES,
        )
