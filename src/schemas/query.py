from pydantic import BaseModel


class CitationOut(BaseModel):
    document_id: str
    document_version_id: str | None = None
    version_number: int | None = None
    file_name: str | None = None
    page: int | None = None
    excerpt: str
    confidence_score: float
    download_url: str | None = None
