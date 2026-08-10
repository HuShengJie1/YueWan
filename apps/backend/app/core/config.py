from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from environment variables and a local .env file."""

    app_env: str = "development"
    app_name: str = "MeetUp Vote API"
    debug: bool = False
    database_url: str = "postgresql+asyncpg://localhost:5432/meetup_vote"
    api_v1_prefix: str = "/api/v1"
    wechat_app_id: str | None = None
    wechat_app_secret: SecretStr | None = None
    jwt_secret: SecretStr | None = None
    jwt_issuer: str = "meetup-vote-api"
    jwt_audience: str = "meetup-vote-miniprogram"
    access_token_ttl_seconds: int = Field(default=7200, ge=60, le=2_592_000)
    media_root: Path = BACKEND_ROOT / "var" / "media"
    media_url_path: str = "/media"
    media_public_base_url: str = "http://127.0.0.1:8000/media"
    avatar_max_upload_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    avatar_max_dimension: int = Field(default=512, ge=64, le=2048)
    avatar_max_source_pixels: int = Field(default=20_000_000, ge=1_000_000, le=100_000_000)
    avatar_jpeg_quality: int = Field(default=85, ge=60, le=95)

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("media_root")
    @classmethod
    def resolve_media_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else BACKEND_ROOT / value

    @field_validator("media_url_path")
    @classmethod
    def validate_media_url_path(cls, value: str) -> str:
        normalized = f"/{value.strip('/')}"
        if normalized == "/":
            raise ValueError("MEDIA_URL_PATH must not mount at the application root")
        return normalized

    @field_validator("media_public_base_url")
    @classmethod
    def normalize_media_public_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("MEDIA_PUBLIC_BASE_URL must be an HTTP(S) URL")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
