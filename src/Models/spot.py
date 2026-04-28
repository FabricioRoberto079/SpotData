from sqlalchemy import LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from src.Models.base_model import BaseModel


class Spot(BaseModel):
    __tablename__ = "spots"

    source_name: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    file_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    extracted_text: Mapped[str] = mapped_column(String, nullable=False)
