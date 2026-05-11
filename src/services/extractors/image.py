import io

from PIL import Image
import pytesseract

from src.interfaces.content_extractor import IContentExtractor


class ImageExtractor(IContentExtractor):
    def from_path(self, file_path: str) -> str:
        return pytesseract.image_to_string(Image.open(file_path)).strip()

    def from_bytes(self, data: bytes) -> str:
        return pytesseract.image_to_string(Image.open(io.BytesIO(data))).strip()
