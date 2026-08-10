from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models.user import User
from app.services.user import UserService

NOW = datetime(2026, 8, 9, 3, 0, tzinfo=UTC)


def make_user() -> User:
    return User(
        id=uuid4(),
        wechat_openid="openid-1",
        wechat_unionid=None,
        display_name="微信用户",
        avatar_url=None,
        is_active=True,
        profile_completed=False,
        last_login_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeUserRepository:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.committed = False
        self.rolled_back = False

    async def update_profile(self, user: User, *, nickname: str) -> User:
        if self.failure is not None:
            raise self.failure
        user.display_name = nickname
        user.profile_completed = True
        return user

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


async def test_update_profile_commits_completed_profile() -> None:
    user = make_user()
    repository = FakeUserRepository()
    service = UserService(repository)  # type: ignore[arg-type]

    result = await service.update_profile(user, nickname="  小林  ")

    assert result is user
    assert user.display_name == "小林"
    assert user.profile_completed
    assert repository.committed
    assert not repository.rolled_back


async def test_update_profile_rolls_back_failure() -> None:
    repository = FakeUserRepository(failure=RuntimeError("database failed"))
    service = UserService(repository)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="database failed"):
        await service.update_profile(make_user(), nickname="小林")

    assert repository.rolled_back
    assert not repository.committed
