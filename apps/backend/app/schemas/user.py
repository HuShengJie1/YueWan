from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

if TYPE_CHECKING:
    from app.models.user import User


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nickname: str | None
    avatar_url: str | None
    profile_completed: bool

    @classmethod
    def from_user(cls, user: "User") -> "UserRead":
        return cls(
            id=user.id,
            nickname=user.display_name if user.profile_completed else None,
            avatar_url=user.avatar_url,
            profile_completed=user.profile_completed,
        )


class UserUpdate(BaseModel):
    nickname: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=24),
    ]
