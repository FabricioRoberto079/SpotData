from datetime import datetime

from sqlalchemy import String, LargeBinary, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from src.Data.postgres_client import Base


class Spot(Base):
    __tablename__ = "spots"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)  # 'foto', 'pdf', 'texto'
    file_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    extracted_text: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
