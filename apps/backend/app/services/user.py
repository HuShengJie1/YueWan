from app.models.user import User
from app.repositories.user import UserRepository


class UserService:
    """Apply current-user profile rules inside a database transaction."""

    def __init__(self, repository: UserRepository) -> None:
        self._users = repository

    async def update_profile(self, user: User, *, nickname: str) -> User:
        try:
            updated_user = await self._users.update_profile(user, nickname=nickname.strip())
            await self._users.commit()
        except Exception:
            await self._users.rollback()
            raise
        return updated_user
