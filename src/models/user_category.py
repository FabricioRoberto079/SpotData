from sqlalchemy import Column, ForeignKey, Table

from src.models.base_model import Base

# Grant table: which users may see/operate inside which categories.
# Admin-managed (see AdminService). Composite PK prevents duplicate grants.
user_categories = Table(
    "user_categories",
    Base.metadata,
    Column(
        "user_id",
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "category_id",
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
