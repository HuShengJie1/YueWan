from typing import TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class ApiResponse[DataT](BaseModel):
    """Standard JSON envelope for versioned API responses."""

    code: int = 0
    message: str = "success"
    data: DataT | None = None


class ApiErrorResponse(BaseModel):
    """Failure envelope used by exception handlers and OpenAPI response declarations."""

    code: int
    message: str
    data: None = None


class HealthStatus(BaseModel):
    status: str
