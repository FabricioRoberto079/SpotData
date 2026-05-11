from pydantic import BaseModel, Field


class CitationOut(BaseModel):
    document_id: str
    document_version_id: str | None = None
    version_number: int | None = None
    file_name: str | None = None
    excerpt: str
    confidence_score: float
    download_url: str | None = None


class QueryAnswer(BaseModel):
    query_id: str
    response_id: str | None = None
    chat_id: str | None = None
    question: str
    status: str
    answer: str | None = None
    citations: list[CitationOut] = Field(default_factory=list)
    time_ms: int | None = None
