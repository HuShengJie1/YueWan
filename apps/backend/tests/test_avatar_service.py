from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.exceptions import (
    AvatarStorageUnavailableError,
    InvalidCloudAvatarFileError,
)
from app.integrations.storage.base import (
    InvalidCloudAvatarReferenceError,
    StoredAvatar,
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
    ) -> None:
        self.save_failure = save_failure
        self.saved_content: bytes | None = None
        self.deleted_urls: list[str] = []

    async def save(self, content: bytes) -> StoredAvatar:
        if self.save_failure is not None:
            raise self.save_failure
        self.saved_content = content
        return StoredAvatar(url="http://testserver/media/avatars/new.jpg")

    async def delete_url(self, url: str) -> None:
        self.deleted_urls.append(url)


class FakeCloudReference:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.resolved: list[tuple[str, str]] = []

    def resolve(self, file_id: str, *, owner_key: str) -> StoredAvatar:
        self.resolved.append((file_id, owner_key))
        if self.failure is not None:
            raise self.failure
        return StoredAvatar(url="https://storage.example.com/avatars/user/avatar.jpg")


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
    )

    with pytest.raises(AvatarStorageUnavailableError):
        await service.update_avatar(make_user(), content=b"source-image")


async def test_avatar_service_commits_validated_cloud_reference() -> None:
    user = make_user()
    repository = FakeRepository()
    reference = FakeCloudReference()
    service = AvatarService(
        repository=repository,  # type: ignore[arg-type]
        storage=None,
        processor=FakeProcessor(),  # type: ignore[arg-type]
        cloud_reference=reference,
    )
    file_id = "cloud://env.bucket/avatars/user/avatar.jpg"

    result = await service.update_avatar_from_cloud(user, file_id=file_id)

    assert result.avatar_url == "https://storage.example.com/avatars/user/avatar.jpg"
    assert reference.resolved == [(file_id, str(user.id))]
    assert repository.committed
    assert not repository.rolled_back


async def test_avatar_service_maps_invalid_cloud_reference() -> None:
    service = AvatarService(
        repository=FakeRepository(),  # type: ignore[arg-type]
        storage=None,
        processor=FakeProcessor(),  # type: ignore[arg-type]
        cloud_reference=FakeCloudReference(failure=InvalidCloudAvatarReferenceError()),
    )

    with pytest.raises(InvalidCloudAvatarFileError):
        await service.update_avatar_from_cloud(
            make_user(),
            file_id="cloud://env.bucket/avatars/user/avatar.jpg",
        )


async def test_avatar_service_rolls_back_cloud_reference_update_failure() -> None:
    repository = FakeRepository(failure=RuntimeError("database failed"))
    service = AvatarService(
        repository=repository,  # type: ignore[arg-type]
        storage=None,
        processor=FakeProcessor(),  # type: ignore[arg-type]
        cloud_reference=FakeCloudReference(),
    )

    with pytest.raises(RuntimeError, match="database failed"):
        await service.update_avatar_from_cloud(
            make_user(),
            file_id="cloud://env.bucket/avatars/user/avatar.jpg",
        )

    assert repository.rolled_back
    assert not repository.committed
