from fastapi import APIRouter

from app.schemas.common import ApiResponse, HealthStatus

router = APIRouter()


@router.get("/health", response_model=ApiResponse[HealthStatus])
async def api_health() -> ApiResponse[HealthStatus]:
    """Verify that the versioned API router is available."""
    return ApiResponse(data=HealthStatus(status="ok"))
