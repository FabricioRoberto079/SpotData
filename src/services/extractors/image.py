import io

import pytesseract
from PIL import Image

from src.interfaces.content_extractor import IContentExtractor


class ImageExtractor(IContentExtractor):
    def from_bytes(self, data: bytes) -> str:
        return pytesseract.image_to_string(Image.open(io.BytesIO(data))).strip()
