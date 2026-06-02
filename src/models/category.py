from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base_model import BaseModel
from src.models.user_category import user_categories


class Category(BaseModel):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    users: Mapped[list["User"]] = relationship(
        secondary=user_categories, back_populates="assigned_categories"
    )
