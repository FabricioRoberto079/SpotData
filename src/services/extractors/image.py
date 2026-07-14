import io

import pytesseract
from PIL import Image


class ImageExtractor:
    def from_bytes(self, data: bytes) -> str:
        return pytesseract.image_to_string(Image.open(io.BytesIO(data))).strip()

    def pages_from_bytes(self, data: bytes) -> list[str] | None:
        return None
