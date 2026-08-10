from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, StringConstraints, field_validator

from app.models.enums import GroupMemberRole
from app.models.group import Group

GroupName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
]
InviteToken = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
]


class GroupCreate(BaseModel):
    name: GroupName
    description: str | None = None

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        normalized = value.strip()
        if len(normalized) > 200:
            raise ValueError("description must contain at most 200 characters")
        return normalized or None


class GroupRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    current_user_role: GroupMemberRole
    member_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_group(
        cls,
        group: Group,
        *,
        current_user_role: GroupMemberRole,
        member_count: int,
    ) -> "GroupRead":
        return cls(
            id=group.id,
            name=group.name,
            description=group.description,
            current_user_role=current_user_role,
            member_count=member_count,
            created_at=group.created_at,
            updated_at=group.updated_at,
        )


class GroupListData(BaseModel):
    items: list[GroupRead]
    next_cursor: str | None
    has_more: bool


class GroupMemberRead(BaseModel):
    user_id: UUID
    nickname: str
    avatar_url: str | None
    role: GroupMemberRole
    joined_at: datetime


class GroupMemberListData(BaseModel):
    items: list[GroupMemberRead]
    next_cursor: str | None
    has_more: bool


class GroupInviteTokenRead(BaseModel):
    invite_token: str
    expires_at: datetime


class JoinGroupRequest(BaseModel):
    invite_token: InviteToken


class DeleteGroupRequest(BaseModel):
    confirmation_name: str
