import logging
import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import (
    AvatarFileTooLargeError,
    AvatarStorageUnavailableError,
    InvalidAvatarImageError,
    InvalidCloudAvatarFileError,
    UnsupportedAvatarTypeError,
)
from app.integrations.storage.base import (
    AvatarStorage,
    InvalidTemporaryAvatarError,
    StoredAvatar,
    TemporaryAvatarSource,
    TemporaryAvatarTooLargeError,
)
from app.models.user import User
from app.repositories.user import UserRepository

logger = logging.getLogger(__name__)
SUPPORTED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


@dataclass(frozen=True, slots=True)
class ProcessedAvatar:
    content: bytes
    width: int
    height: int


class AvatarImageProcessor:
    """Validate, resize, strip metadata, and normalize an avatar to JPEG."""

    def __init__(
        self,
        *,
        max_upload_bytes: int,
        max_dimension: int,
        max_source_pixels: int,
        jpeg_quality: int,
    ) -> None:
        self._max_upload_bytes = max_upload_bytes
        self._max_dimension = max_dimension
        self._max_source_pixels = max_source_pixels
        self._jpeg_quality = jpeg_quality

    def process(self, content: bytes) -> ProcessedAvatar:
        if len(content) > self._max_upload_bytes:
            raise AvatarFileTooLargeError
        if not content:
            raise InvalidAvatarImageError

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as source:
                    if source.format not in SUPPORTED_IMAGE_FORMATS:
                        raise UnsupportedAvatarTypeError
                    width, height = source.size
                    if width < 1 or height < 1:
                        raise InvalidAvatarImageError
                    if width * height > self._max_source_pixels:
                        raise AvatarFileTooLargeError

                    source.load()
                    transposed = ImageOps.exif_transpose(source)
                    normalized = self._flatten_to_rgb(transposed)
                    try:
                        normalized.thumbnail(
                            (self._max_dimension, self._max_dimension),
                            Image.Resampling.LANCZOS,
                        )
                        output = BytesIO()
                        normalized.save(
                            output,
                            format="JPEG",
                            quality=self._jpeg_quality,
                            optimize=True,
                        )
                        return ProcessedAvatar(
                            content=output.getvalue(),
                            width=normalized.width,
                            height=normalized.height,
                        )
                    finally:
                        normalized.close()
                        if transposed is not source:
                            transposed.close()
        except (AvatarFileTooLargeError, InvalidAvatarImageError, UnsupportedAvatarTypeError):
            raise
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            OSError,
            UnidentifiedImageError,
            ValueError,
        ) as exc:
            raise InvalidAvatarImageError from exc

    @staticmethod
    def _flatten_to_rgb(image: Image.Image) -> Image.Image:
        if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
            rgba = image.convert("RGBA")
            try:
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                return background
            finally:
                rgba.close()
        return image.convert("RGB")


class AvatarService:
    """Coordinate image processing, storage, and the User database transaction."""

    def __init__(
        self,
        *,
        repository: UserRepository,
        storage: AvatarStorage,
        processor: AvatarImageProcessor,
        temporary_source: TemporaryAvatarSource | None = None,
        max_upload_bytes: int,
    ) -> None:
        self._users = repository
        self._storage = storage
        self._processor = processor
        self._temporary_source = temporary_source
        self._max_upload_bytes = max_upload_bytes

    async def update_avatar_from_cloud(self, user: User, *, file_id: str) -> User:
        if self._temporary_source is None:
            logger.error(
                "Cloud avatar endpoint was called without a cloud temporary source; "
                "check AVATAR_STORAGE_BACKEND"
            )
            raise AvatarStorageUnavailableError
        try:
            content = await self._temporary_source.read_temporary(
                file_id,
                owner_key=str(user.id),
                max_bytes=self._max_upload_bytes,
            )
        except TemporaryAvatarTooLargeError as exc:
            await self._delete_temporary_without_masking_error(file_id)
            raise AvatarFileTooLargeError from exc
        except InvalidTemporaryAvatarError as exc:
            raise InvalidCloudAvatarFileError from exc
        except OSError as exc:
            logger.exception("Failed to read temporary CloudBase avatar")
            await self._delete_temporary_without_masking_error(file_id)
            raise AvatarStorageUnavailableError from exc

        try:
            return await self.update_avatar(user, content=content)
        finally:
            await self._delete_temporary_without_masking_error(file_id)

    async def update_avatar(self, user: User, *, content: bytes) -> User:
        processed = await run_in_threadpool(self._processor.process, content)
        try:
            stored = await self._storage.save(processed.content)
        except OSError as exc:
            logger.exception("Failed to store processed avatar")
            raise AvatarStorageUnavailableError from exc

        old_avatar_url = user.avatar_url
        try:
            updated_user = await self._users.update_avatar(user, avatar_url=stored.url)
            await self._users.commit()
        except Exception:
            await self._users.rollback()
            await self._delete_without_masking_error(stored)
            raise

        if old_avatar_url and old_avatar_url != stored.url:
            await self._delete_without_masking_error(StoredAvatar(url=old_avatar_url))
        return updated_user

    async def _delete_without_masking_error(self, avatar: StoredAvatar) -> None:
        try:
            await self._storage.delete_url(avatar.url)
        except OSError:
            logger.exception("Failed to remove a managed avatar file")

    async def _delete_temporary_without_masking_error(self, file_id: str) -> None:
        if self._temporary_source is None:
            return
        try:
            await self._temporary_source.delete_file_id(file_id)
        except OSError:
            logger.exception("Failed to remove a temporary cloud avatar")
