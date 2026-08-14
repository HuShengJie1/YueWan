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
    CloudAvatarReference,
    InvalidCloudAvatarReferenceError,
    StoredAvatar,
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
        storage: AvatarStorage | None,
        processor: AvatarImageProcessor,
        cloud_reference: CloudAvatarReference | None = None,
    ) -> None:
        self._users = repository
        self._storage = storage
        self._processor = processor
        self._cloud_reference = cloud_reference

    async def update_avatar_from_cloud(self, user: User, *, file_id: str) -> User:
        if self._cloud_reference is None:
            logger.error("Cloud avatar endpoint was called without a cloud reference resolver")
            raise AvatarStorageUnavailableError
        try:
            stored = self._cloud_reference.resolve(file_id, owner_key=str(user.id))
        except InvalidCloudAvatarReferenceError as exc:
            raise InvalidCloudAvatarFileError from exc

        try:
            updated_user = await self._users.update_avatar(user, avatar_url=stored.url)
            await self._users.commit()
        except Exception:
            await self._users.rollback()
            raise
        return updated_user

    async def update_avatar(self, user: User, *, content: bytes) -> User:
        if self._storage is None:
            raise AvatarStorageUnavailableError
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
        if self._storage is None:
            return
        try:
            await self._storage.delete_url(avatar.url)
        except OSError:
            logger.exception("Failed to remove a managed avatar file")
