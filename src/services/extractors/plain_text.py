from src.interfaces.content_extractor import IContentExtractor


class PlainTextExtractor(IContentExtractor):
    def from_path(self, file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    def from_bytes(self, data: bytes) -> str:
        return data.decode("utf-8").strip()
