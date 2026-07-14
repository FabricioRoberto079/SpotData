from fastapi import UploadFile

from src.exceptions import ValidationError
from src.protocols.upload_strategy import UploadPayload
from src.services.upload_strategies._shared import (
    FILE_EXTENSION_MAP,
    clean_optional,
    extract_ext,
    read_upload,
    validate_mime_for_ext,
)


class FileUploadStrategy:
    async def build_payload(
        self,
        *,
        file: UploadFile | None,
        text: str | None,
        file_name: str | None,
    ) -> UploadPayload:
        if file is None:
            raise ValidationError("Missing 'file' for file upload.")
        filename = file.filename or ""
        ext = extract_ext(filename)
        mapping = FILE_EXTENSION_MAP.get(ext)
        if mapping is None:
            raise ValidationError(
                f"Unsupported file extension '{ext}'. "
                f"Accepted: {', '.join(sorted(FILE_EXTENSION_MAP))}."
            )
        content_type, category = mapping
        data = await read_upload(file)
        validate_mime_for_ext(ext, data)
        name = clean_optional(file_name) or filename
        return UploadPayload(
            file_data=data,
            content_type=content_type,
            file_name=name,
            category=category,
        )
