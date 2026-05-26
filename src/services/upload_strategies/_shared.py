import magic
from fastapi import UploadFile

from src.exceptions import ValidationError

MAX_UPLOAD_SIZE = 15 * 1024 * 1024

# Allowed MIME types per declared extension. python-magic inspects the actual bytes,
# so renaming a `malware.exe` to `report.pdf` will be caught here.
ALLOWED_MIMES_BY_EXT: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".doc": {"application/msword", "application/vnd.ms-office", "application/x-ole-storage"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    ".txt": {"text/plain"},
    ".md": {"text/plain", "text/markdown"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
}


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def extract_ext(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def detect_mime(data: bytes) -> str:
    """Return the MIME type inferred from the bytes (libmagic). Empty on failure."""
    try:
        return magic.from_buffer(data, mime=True) or ""
    except Exception:
        return ""


def validate_mime_for_ext(ext: str, data: bytes) -> None:
    """Raise ValidationError if the file's magic bytes don't match the declared extension."""
    allowed = ALLOWED_MIMES_BY_EXT.get(ext)
    if not allowed:
        return  # Unknown extension is rejected upstream.
    mime = detect_mime(data)
    if mime and mime not in allowed:
        raise ValidationError(
            f"File contents don't match extension '{ext}' "
            f"(detected '{mime}', expected {sorted(allowed)})."
        )


_READ_CHUNK = 64 * 1024


async def read_upload(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_SIZE:
            raise ValidationError(
                f"File exceeds {MAX_UPLOAD_SIZE // (1024 * 1024)}MB limit."
            )
        chunks.append(chunk)
    if total == 0:
        raise ValidationError("Empty file.")
    return b"".join(chunks)
