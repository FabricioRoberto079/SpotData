import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from docx import Document

from src.exceptions import ValidationError
from src.interfaces.content_extractor import IContentExtractor

DOCX_MAGIC = b"PK\x03\x04"
DOC_MAGIC = b"\xd0\xcf\x11\xe0"


class WordExtractor(IContentExtractor):
    def from_path(self, file_path: str) -> str:
        with open(file_path, "rb") as f:
            return self.from_bytes(f.read())

    def from_bytes(self, data: bytes) -> str:
        if data.startswith(DOCX_MAGIC):
            return self._extract_docx(data)
        if data.startswith(DOC_MAGIC):
            return self._extract_doc(data)
        raise ValidationError(
            "Word format not recognized. Expected .doc or .docx."
        )

    @staticmethod
    def _extract_docx(data: bytes) -> str:
        document = Document(io.BytesIO(data))
        parts: list[str] = []
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if text:
                parts.append(text)
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
        return "\n".join(parts).strip()

    @staticmethod
    def _extract_doc(data: bytes) -> str:
        if shutil.which("antiword") is None:
            raise ValidationError(
                "Support for .doc requires the 'antiword' utility installed on the system."
            )
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            result = subprocess.run(
                ["antiword", tmp_path],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as exc:
            raise ValidationError(
                f"Failed to extract text from .doc: {exc.stderr.strip() or exc}"
            ) from exc
        finally:
            Path(tmp_path).unlink(missing_ok=True)
