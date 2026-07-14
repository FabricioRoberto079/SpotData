from sqlalchemy import ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from src.enums.upload_session_status import UploadSessionStatus
from src.models.base import TimestampedBase


class UploadSession(TimestampedBase):
    """A resumable upload in progress: bytes accumulate in ``data`` until
    ``bytes_received == total_size``, then completion runs the regular
    ingestion pipeline and clears the blob."""

    __tablename__ = "upload_sessions"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=True
    )
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    total_size: Mapped[int] = mapped_column(Integer, nullable=False)
    bytes_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=UploadSessionStatus.ACTIVE.value
    )
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, default=b"")
