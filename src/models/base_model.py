import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _default_updated_at(context) -> datetime:
    params = context.get_current_parameters() or {}
    return params.get("created_at") or datetime.now(UTC)


class BaseModel(Base):
    __abstract__ = True

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_default_updated_at,
        onupdate=lambda: datetime.now(UTC),
    )
