import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.group_security import HangoutPageCursor, SignedCursorCodec
from app.db.session import engine
from app.models.enums import GroupMemberRole, GroupMemberStatus, HangoutStatus
from app.models.group import Group, GroupMember
from app.models.hangout import Hangout
from app.models.user import User
from app.repositories.hangout import HangoutRepository
from app.services.hangout import HangoutService

pytestmark = [
    pytest.mark.skipif(
        os.getenv("RUN_DATABASE_TESTS") != "1",
        reason="set RUN_DATABASE_TESTS=1 when a migrated MySQL test database is available",
    ),
    pytest.mark.asyncio(loop_scope="session"),
]

NOW = datetime(2026, 8, 10, 3, 0, tzinfo=UTC)
SECRET = "test-secret-that-is-at-least-32-bytes-long"


def make_user(*, nickname: str) -> User:
    suffix = uuid4().hex
    return User(
        wechat_openid=f"hangout-test-openid-{suffix}",
        wechat_unionid=None,
        display_name=nickname,
        avatar_url=None,
        is_active=True,
        profile_completed=True,
        last_login_at=NOW,
    )


async def test_repository_filters_membership_scopes_detail_and_pages_stably() -> None:
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                owner = make_user(nickname="Owner")
                member = make_user(nickname="Member")
                left_member = make_user(nickname="Left")
                session.add_all([owner, member, left_member])
                await session.flush()

                group = Group(name="Hangout Group", description=None, created_by_user_id=owner.id)
                other_group = Group(
                    name="Other Group",
                    description=None,
                    created_by_user_id=owner.id,
                )
                session.add_all([group, other_group])
                await session.flush()
                session.add_all(
                    [
                        GroupMember(
                            group_id=group.id,
                            user_id=owner.id,
                            role=GroupMemberRole.OWNER,
                            status=GroupMemberStatus.ACTIVE,
                            left_at=None,
                        ),
                        GroupMember(
                            group_id=group.id,
                            user_id=member.id,
                            role=GroupMemberRole.MEMBER,
                            status=GroupMemberStatus.ACTIVE,
                            left_at=None,
                        ),
                        GroupMember(
                            group_id=group.id,
                            user_id=left_member.id,
                            role=GroupMemberRole.MEMBER,
                            status=GroupMemberStatus.LEFT,
                            left_at=NOW,
                        ),
                    ]
                )
                hangouts = [
                    Hangout(
                        group_id=group.id,
                        created_by_user_id=owner.id,
                        title=f"Hangout {number}",
                        description=None,
                        status=status,
                        voting_deadline=None,
                        confirmed_at=None,
                        cancelled_at=None,
                    )
                    for number, status in enumerate(
                        [HangoutStatus.DRAFT, HangoutStatus.VOTING, HangoutStatus.CANCELLED]
                    )
                ]
                other_hangout = Hangout(
                    group_id=other_group.id,
                    created_by_user_id=owner.id,
                    title="Other",
                    description=None,
                    status=HangoutStatus.DRAFT,
                    voting_deadline=None,
                    confirmed_at=None,
                    cancelled_at=None,
                )
                session.add_all([*hangouts, other_hangout])
                await session.flush()
                await session.execute(
                    update(Hangout)
                    .where(Hangout.id.in_([item.id for item in hangouts]))
                    .values(created_at=NOW)
                )
                await session.commit()

                repository = HangoutRepository(session)
                assert await repository.get_active_membership(group_id=group.id, user_id=member.id)
                assert (
                    await repository.get_active_membership(
                        group_id=group.id, user_id=left_member.id
                    )
                    is None
                )

                first_page = await repository.list_in_group(
                    group_id=group.id,
                    after=None,
                    limit=2,
                )
                second_page = await repository.list_in_group(
                    group_id=group.id,
                    after=HangoutPageCursor(
                        created_at=first_page[-1].created_at,
                        hangout_id=first_page[-1].id,
                    ),
                    limit=2,
                )
                all_rows = first_page + second_page
                assert [row.id for row in all_rows] == sorted(
                    [row.id for row in hangouts], reverse=True
                )
                assert {row.status for row in all_rows} == {
                    HangoutStatus.DRAFT,
                    HangoutStatus.VOTING,
                    HangoutStatus.CANCELLED,
                }
                assert other_hangout.id not in {row.id for row in all_rows}
                assert (
                    await repository.get_in_group(
                        group_id=group.id,
                        hangout_id=other_hangout.id,
                    )
                    is None
                )
        finally:
            await outer_transaction.rollback()


async def test_service_create_commits_and_failed_update_rolls_back() -> None:
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                owner = make_user(nickname="Owner")
                session.add(owner)
                await session.flush()
                group = Group(name="Transactions", description=None, created_by_user_id=owner.id)
                session.add(group)
                await session.flush()
                session.add(
                    GroupMember(
                        group_id=group.id,
                        user_id=owner.id,
                        role=GroupMemberRole.OWNER,
                        status=GroupMemberStatus.ACTIVE,
                        left_at=None,
                    )
                )
                await session.commit()

                service = HangoutService(
                    repository=HangoutRepository(session),
                    cursors=SignedCursorCodec(secret=SECRET),
                )
                created = await service.create_hangout(
                    owner,
                    group_id=group.id,
                    title="Committed",
                    description=None,
                    voting_deadline=None,
                )
                assert (
                    await session.scalar(
                        select(func.count(Hangout.id)).where(Hangout.id == created.id)
                    )
                    == 1
                )

                class FailingCommitRepository(HangoutRepository):
                    async def commit(self) -> None:
                        raise RuntimeError("simulated commit failure")

                failing_service = HangoutService(
                    repository=FailingCommitRepository(session),
                    cursors=SignedCursorCodec(secret=SECRET),
                )
                with pytest.raises(RuntimeError, match="simulated commit failure"):
                    await failing_service.update_hangout(
                        owner,
                        group_id=group.id,
                        hangout_id=created.id,
                        title="Must Roll Back",
                        description=None,
                        voting_deadline=None,
                    )
                await session.refresh(created)
                assert created.title == "Committed"
        finally:
            await outer_transaction.rollback()
