from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: str
    file_name: str
    category: str
    uploaded_by: str | None = None
    uploaded_at: str | None = None
    versions_count: int
    latest_version: int | None = None
    latest_status: str | None = None


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int
    limit: int
    offset: int


class DocumentVersionOut(BaseModel):
    id: str
    version_number: int
    content_type: str
    vectorization_status: str
    created_at: str | None = None


class SearchHit(BaseModel):
    vector_id: str
    document_id: str | None = None
    version_number: int | None = None
    chunk_index: int | None = None
    file_name: str | None = None
    content_type: str | None = None
    distance: float
    snippet: str


class SearchResults(BaseModel):
    query: str
    results: list[SearchHit] = Field(default_factory=list)
