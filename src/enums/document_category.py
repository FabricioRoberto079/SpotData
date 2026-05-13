from enum import StrEnum


class DocumentCategory(StrEnum):
    DOCUMENTS = "documents"
    IMAGES = "images"
    TEXT = "text"


_EXTENSION_TO_CATEGORY = {
    ".pdf": DocumentCategory.DOCUMENTS,
    ".doc": DocumentCategory.DOCUMENTS,
    ".docx": DocumentCategory.DOCUMENTS,
    ".png": DocumentCategory.IMAGES,
    ".jpg": DocumentCategory.IMAGES,
    ".jpeg": DocumentCategory.IMAGES,
    ".txt": DocumentCategory.TEXT,
    ".md": DocumentCategory.TEXT,
}


def category_from_filename(filename: str) -> DocumentCategory | None:
    if "." not in filename:
        return None
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    return _EXTENSION_TO_CATEGORY.get(ext)
