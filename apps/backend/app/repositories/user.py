from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
        existing = await self._get_by_openid_for_update(openid)
        if existing is not None:
            return await self._record_login(
                existing,
                unionid=unionid,
                logged_in_at=logged_in_at,
            )

        candidate = User(
            wechat_openid=openid,
            wechat_unionid=unionid,
            display_name=DEFAULT_DISPLAY_NAME,
            last_login_at=logged_in_at,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(candidate)
                await self._session.flush()
        except IntegrityError:
            # Concurrent first logins race on openid. A savepoint keeps the outer
            # login transaction usable; unionid conflicts remain real errors.
            existing = await self._get_by_openid_for_update(openid)
            if existing is None:
                raise
            return await self._record_login(
                existing,
                unionid=unionid,
                logged_in_at=logged_in_at,
            )
        return candidate

    async def _get_by_openid_for_update(self, openid: str) -> User | None:
        statement = select(User).where(User.wechat_openid == openid).with_for_update()
        return (await self._session.scalars(statement)).one_or_none()

    async def _record_login(
        self,
        user: User,
        *,
        unionid: str | None,
        logged_in_at: datetime,
    ) -> User:
        if user.wechat_unionid is None:
            user.wechat_unionid = unionid
        user.last_login_at = logged_in_at
        user.updated_at = logged_in_at
        await self._session.flush()
        return user

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
