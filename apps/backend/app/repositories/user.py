from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

DEFAULT_DISPLAY_NAME = "微信用户"


class UserRepository:
    """Persist and retrieve users without owning business flow decisions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_wechat_user(
        self,
        *,
        openid: str,
        unionid: str | None,
        logged_in_at: datetime,
    ) -> User:
        statement = insert(User).values(
            wechat_openid=openid,
            wechat_unionid=unionid,
            display_name=DEFAULT_DISPLAY_NAME,
            last_login_at=logged_in_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[User.wechat_openid],
            set_={
                "wechat_unionid": func.coalesce(
                    User.wechat_unionid,
                    statement.excluded.wechat_unionid,
                ),
                "last_login_at": logged_in_at,
                "updated_at": logged_in_at,
            },
        ).returning(User)
        statement = statement.execution_options(populate_existing=True)
        result = await self._session.execute(statement)
        return result.scalar_one()

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def update_profile(self, user: User, *, nickname: str) -> User:
        user.display_name = nickname
        user.profile_completed = True
        await self._session.flush()
        return user

    async def update_avatar(self, user: User, *, avatar_url: str) -> User:
        user.avatar_url = avatar_url
        await self._session.flush()
        return user

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
