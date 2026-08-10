from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.errors import register_exception_handlers
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.schemas.common import HealthStatus


def create_app() -> FastAPI:
    """Create the FastAPI application without opening external connections."""
    settings = get_settings()
    configure_logging(debug=settings.debug)

    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        docs_url=f"{settings.api_v1_prefix}/docs",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        redoc_url=None,
    )

    @application.get("/health", response_model=HealthStatus, tags=["system"])
    async def root_health() -> HealthStatus:
        return HealthStatus(status="ok")

    settings.media_root.mkdir(parents=True, exist_ok=True)
    register_exception_handlers(application)
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    application.mount(
        settings.media_url_path,
        StaticFiles(directory=settings.media_root),
        name="media",
    )
    return application


app = create_app()
