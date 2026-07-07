from pydantic import BaseModel, Field


class UploadSessionCreate(BaseModel):
    file_name: str = Field(description="Target file name, extension included.")
    total_size: int = Field(description="Exact size of the file in bytes.")
    category_id: str | None = Field(
        default=None,
        description="Optional target category id. Omit to share with everyone.",
    )


class UploadSessionOut(BaseModel):
    id: str
    file_name: str
    category_id: str | None = None
    total_size: int
    bytes_received: int
    next_offset: int
    status: str
