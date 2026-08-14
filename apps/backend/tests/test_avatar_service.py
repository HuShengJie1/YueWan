from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.exceptions import (
    AvatarFileTooLargeError,
    AvatarStorageUnavailableError,
    InvalidCloudAvatarFileError,
)
from app.integrations.storage.base import (
    InvalidTemporaryAvatarError,
    StoredAvatar,
    TemporaryAvatarTooLargeError,
)
from app.models.user import User
from app.services.avatar import AvatarService, ProcessedAvatar

NOW = datetime(2026, 8, 9, 3, 0, tzinfo=UTC)


def make_user(*, avatar_url: str | None = None) -> User:
    return User(
        id=uuid4(),
        wechat_openid="openid-1",
        wechat_unionid=None,
        display_name="微信用户",
        avatar_url=avatar_url,
        is_active=True,
        profile_completed=False,
        last_login_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeProcessor:
    def process(self, content: bytes) -> ProcessedAvatar:
        assert content == b"source-image"
        return ProcessedAvatar(content=b"processed-jpeg", width=256, height=256)


class FakeStorage:
    def __init__(
        self,
        *,
        save_failure: OSError | None = None,
        read_failure: Exception | None = None,
    ) -> None:
        self.save_failure = save_failure
        self.read_failure = read_failure
        self.saved_content: bytes | None = None
        self.deleted_urls: list[str] = []
        self.deleted_file_ids: list[str] = []

    async def save(self, content: bytes) -> StoredAvatar:
        if self.save_failure is not None:
            raise self.save_failure
        self.saved_content = content
        return StoredAvatar(url="http://testserver/media/avatars/new.jpg")

    async def delete_url(self, url: str) -> None:
        self.deleted_urls.append(url)

    async def read_temporary(
        self,
        file_id: str,
        *,
        owner_key: str,
        max_bytes: int,
    ) -> bytes:
        assert file_id == "cloud://env.bucket/avatar-uploads/user/source"
        assert owner_key
        assert max_bytes == 5 * 1024 * 1024
        if self.read_failure is not None:
            raise self.read_failure
        return b"source-image"

    async def delete_file_id(self, file_id: str) -> None:
        self.deleted_file_ids.append(file_id)


class FakeRepository:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.committed = False
        self.rolled_back = False

    async def update_avatar(self, user: User, *, avatar_url: str) -> User:
        if self.failure is not None:
            raise self.failure
        user.avatar_url = avatar_url
        return user

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


async def test_avatar_service_commits_new_avatar_and_removes_old_managed_url() -> None:
    old_url = "http://testserver/media/avatars/old.jpg"
    user = make_user(avatar_url=old_url)
    repository = FakeRepository()
    storage = FakeStorage()
    service = AvatarService(
        repository=repository,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        processor=FakeProcessor(),  # type: ignore[arg-type]
        max_upload_bytes=5 * 1024 * 1024,
    )

    result = await service.update_avatar(user, content=b"source-image")

    assert result is user
    assert user.avatar_url == "http://testserver/media/avatars/new.jpg"
    assert storage.saved_content == b"processed-jpeg"
    assert storage.deleted_urls == [old_url]
    assert repository.committed
    assert not repository.rolled_back


async def test_avatar_service_removes_new_file_when_database_update_fails() -> None:
    repository = FakeRepository(failure=RuntimeError("database failed"))
    storage = FakeStorage()
    service = AvatarService(
        repository=repository,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        processor=FakeProcessor(),  # type: ignore[arg-type]
        max_upload_bytes=5 * 1024 * 1024,
    )

    with pytest.raises(RuntimeError, match="database failed"):
        await service.update_avatar(make_user(), content=b"source-image")

    assert repository.rolled_back
    assert not repository.committed
    assert storage.deleted_urls == ["http://testserver/media/avatars/new.jpg"]


async def test_avatar_service_maps_storage_failures() -> None:
    service = AvatarService(
        repository=FakeRepository(),  # type: ignore[arg-type]
        storage=FakeStorage(save_failure=OSError("disk unavailable")),  # type: ignore[arg-type]
        processor=FakeProcessor(),  # type: ignore[arg-type]
        max_upload_bytes=5 * 1024 * 1024,
    )

    with pytest.raises(AvatarStorageUnavailableError):
        await service.update_avatar(make_user(), content=b"source-image")


async def test_avatar_service_imports_cloud_file_and_always_removes_temporary_object() -> None:
    user = make_user()
    storage = FakeStorage()
    service = AvatarService(
        repository=FakeRepository(),  # type: ignore[arg-type]
        storage=storage,
        processor=FakeProcessor(),  # type: ignore[arg-type]
        temporary_source=storage,
        max_upload_bytes=5 * 1024 * 1024,
    )
    file_id = "cloud://env.bucket/avatar-uploads/user/source"

    result = await service.update_avatar_from_cloud(user, file_id=file_id)

    assert result.avatar_url == "http://testserver/media/avatars/new.jpg"
    assert storage.deleted_file_ids == [file_id]


@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        (InvalidTemporaryAvatarError(), InvalidCloudAvatarFileError),
        (TemporaryAvatarTooLargeError(), AvatarFileTooLargeError),
        (OSError("cloud unavailable"), AvatarStorageUnavailableError),
    ],
)
async def test_avatar_service_maps_cloud_source_failures(
    failure: Exception,
    expected_error: type[Exception],
) -> None:
    storage = FakeStorage(read_failure=failure)
    service = AvatarService(
        repository=FakeRepository(),  # type: ignore[arg-type]
        storage=storage,
        processor=FakeProcessor(),  # type: ignore[arg-type]
        temporary_source=storage,
        max_upload_bytes=5 * 1024 * 1024,
    )

    with pytest.raises(expected_error):
        await service.update_avatar_from_cloud(
            make_user(),
            file_id="cloud://env.bucket/avatar-uploads/user/source",
        )
