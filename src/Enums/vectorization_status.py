from enum import StrEnum


class VectorizationStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    ERROR = "error"
