from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base_model import BaseModel


class DocumentFolder(BaseModel):
    __tablename__ = "document_folders"

    name: Mapped[str] = mapped_column(String, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_folders.id"), nullable=True
    )
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    parent: Mapped["DocumentFolder | None"] = relationship(
        back_populates="children", remote_side="DocumentFolder.id"
    )
    children: Mapped[list["DocumentFolder"]] = relationship(back_populates="parent")
    documents: Mapped[list["KnowledgeDocument"]] = relationship(back_populates="folder")
