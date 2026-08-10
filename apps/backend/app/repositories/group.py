from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.group_security import PageCursor
from app.models.enums import GroupMemberRole, GroupMemberStatus
from app.models.group import Group, GroupMember
from app.models.user import User


@dataclass(frozen=True, slots=True)
class GroupSummary:
    group: Group
    current_user_role: GroupMemberRole
    member_count: int
    joined_at: datetime
    membership_id: UUID


@dataclass(frozen=True, slots=True)
class GroupMemberSummary:
    user_id: UUID
    nickname: str
    avatar_url: str | None
    role: GroupMemberRole
    joined_at: datetime
    membership_id: UUID


@dataclass(frozen=True, slots=True)
class GroupDeleteTarget:
    group: Group
    current_user_role: GroupMemberRole


class GroupRepository:
    """Persist group membership and execute set-based group read queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_with_owner(
        self,
        *,
        user_id: UUID,
        name: str,
        description: str | None,
    ) -> GroupSummary:
        group = Group(name=name, description=description, created_by_user_id=user_id)
        self._session.add(group)
        await self._session.flush()
        owner = GroupMember(
            group_id=group.id,
            user_id=user_id,
            role=GroupMemberRole.OWNER,
            status=GroupMemberStatus.ACTIVE,
            left_at=None,
        )
        self._session.add(owner)
        await self._session.flush()
        return GroupSummary(
            group=group,
            current_user_role=owner.role,
            member_count=1,
            joined_at=owner.created_at,
            membership_id=owner.id,
        )

    async def list_active_groups(
        self,
        *,
        user_id: UUID,
        after: PageCursor | None,
        limit: int,
    ) -> list[GroupSummary]:
        membership = aliased(GroupMember)
        member_count = self._active_member_count_subquery()
        statement = (
            select(
                Group,
                membership.role,
                member_count.label("member_count"),
                membership.created_at,
                membership.id,
            )
            .join(
                membership,
                and_(
                    membership.group_id == Group.id,
                    membership.user_id == user_id,
                    membership.status == GroupMemberStatus.ACTIVE,
                ),
            )
            .order_by(membership.created_at.desc(), membership.id.desc())
            .limit(limit)
        )
        if after is not None:
            statement = statement.where(
                or_(
                    membership.created_at < after.joined_at,
                    and_(
                        membership.created_at == after.joined_at,
                        membership.id < after.membership_id,
                    ),
                )
            )

        rows = (await self._session.execute(statement)).all()
        return [
            GroupSummary(
                group=row[0],
                current_user_role=row[1],
                member_count=row[2],
                joined_at=row[3],
                membership_id=row[4],
            )
            for row in rows
        ]

    async def get_active_group(
        self,
        *,
        group_id: UUID,
        user_id: UUID,
    ) -> GroupSummary | None:
        membership = aliased(GroupMember)
        member_count = self._active_member_count_subquery()
        statement = (
            select(
                Group,
                membership.role,
                member_count.label("member_count"),
                membership.created_at,
                membership.id,
            )
            .join(
                membership,
                and_(
                    membership.group_id == Group.id,
                    membership.user_id == user_id,
                    membership.status == GroupMemberStatus.ACTIVE,
                ),
            )
            .where(Group.id == group_id)
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        return GroupSummary(
            group=row[0],
            current_user_role=row[1],
            member_count=row[2],
            joined_at=row[3],
            membership_id=row[4],
        )

    async def list_active_members(
        self,
        *,
        group_id: UUID,
        after: PageCursor | None,
        limit: int,
    ) -> list[GroupMemberSummary]:
        statement = (
            select(
                GroupMember.user_id,
                User.display_name,
                User.avatar_url,
                GroupMember.role,
                GroupMember.created_at,
                GroupMember.id,
            )
            .join(User, User.id == GroupMember.user_id)
            .where(
                GroupMember.group_id == group_id,
                GroupMember.status == GroupMemberStatus.ACTIVE,
            )
            .order_by(GroupMember.created_at.desc(), GroupMember.id.desc())
            .limit(limit)
        )
        if after is not None:
            statement = statement.where(
                or_(
                    GroupMember.created_at < after.joined_at,
                    and_(
                        GroupMember.created_at == after.joined_at,
                        GroupMember.id < after.membership_id,
                    ),
                )
            )
        rows = (await self._session.execute(statement)).all()
        return [
            GroupMemberSummary(
                user_id=row[0],
                nickname=row[1],
                avatar_url=row[2],
                role=row[3],
                joined_at=row[4],
                membership_id=row[5],
            )
            for row in rows
        ]

    async def group_exists(self, group_id: UUID) -> bool:
        statement = select(Group.id).where(Group.id == group_id)
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def get_active_group_for_update(
        self,
        *,
        group_id: UUID,
        user_id: UUID,
    ) -> GroupDeleteTarget | None:
        membership = aliased(GroupMember)
        statement = (
            select(Group, membership.role)
            .join(
                membership,
                and_(
                    membership.group_id == Group.id,
                    membership.user_id == user_id,
                    membership.status == GroupMemberStatus.ACTIVE,
                ),
            )
            .where(Group.id == group_id)
            .with_for_update(of=(Group, membership))
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        return GroupDeleteTarget(group=row[0], current_user_role=row[1])

    async def delete_group(self, group: Group) -> None:
        await self._session.delete(group)
        await self._session.flush()

    async def join_group(self, *, group_id: UUID, user_id: UUID) -> GroupMember:
        statement = insert(GroupMember).values(
            group_id=group_id,
            user_id=user_id,
            role=GroupMemberRole.MEMBER,
            status=GroupMemberStatus.ACTIVE,
            left_at=None,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[GroupMember.group_id, GroupMember.user_id],
            set_={
                "role": GroupMember.role,
                "status": GroupMemberStatus.ACTIVE,
                "left_at": None,
                "updated_at": func.now(),
            },
        ).returning(GroupMember)
        statement = statement.execution_options(populate_existing=True)
        return (await self._session.execute(statement)).scalar_one()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    @staticmethod
    def _active_member_count_subquery():  # type: ignore[no-untyped-def]
        counted_membership = aliased(GroupMember)
        return (
            select(func.count(counted_membership.id))
            .where(
                counted_membership.group_id == Group.id,
                counted_membership.status == GroupMemberStatus.ACTIVE,
            )
            .correlate(Group)
            .scalar_subquery()
        )
