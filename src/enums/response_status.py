from enum import StrEnum


class ResponseStatus(StrEnum):
    SUCCESS = "success"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    NOT_FOUND = "not_found"
    ERROR = "error"
