from pypdf import PdfReader
from PIL import Image
import pytesseract

from src.Enums.content_type import ContentType


def extract_from_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    pages = [page.extract_text() for page in reader.pages if page.extract_text()]
    return "\n".join(pages).strip()


def extract_from_image(file_path: str) -> str:
    image = Image.open(file_path)
    return pytesseract.image_to_string(image).strip()


def extract_text(file_path: str, content_type: ContentType) -> str:
    """Extrai texto baseado no tipo de conteúdo."""
    if content_type == ContentType.TEXTO:
        with open(file_path, "r") as f:
            return f.read().strip()
    elif content_type == ContentType.PDF:
        return extract_from_pdf(file_path)
    elif content_type == ContentType.FOTO:
        return extract_from_image(file_path)
    else:
        raise ValueError(f"Tipo não suportado: {content_type}")
