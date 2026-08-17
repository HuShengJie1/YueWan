import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, event, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import GroupNotFoundError
from app.core.group_security import GroupInviteTokenService, PageCursor, SignedCursorCodec
from app.db.session import async_session_factory, engine
from app.models.enums import (
    GroupMemberRole,
    GroupMemberStatus,
    HangoutStatus,
    ProposalVoteValue,
)
from app.models.event import Event
from app.models.group import Group, GroupMember
from app.models.hangout import Hangout
from app.models.proposal import Proposal, ProposalVote
from app.models.time_option import TimeOption, TimeVote
from app.models.user import User
from app.repositories.group import GroupRepository
from app.services.group import GroupService

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
        wechat_openid=f"group-test-openid-{suffix}",
        wechat_unionid=None,
        display_name=nickname,
        avatar_url=None,
        is_active=True,
        profile_completed=True,
        last_login_at=NOW,
    )


async def test_repository_filters_active_groups_counts_members_and_pages_stably() -> None:
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                owner = make_user(nickname="Owner")
                active_friend = make_user(nickname="Active Friend")
                left_friend = make_user(nickname="Left Friend")
                other_owner = make_user(nickname="Other Owner")
                session.add_all([owner, active_friend, left_friend, other_owner])
                await session.flush()

                repository = GroupRepository(session)
                owned = await repository.create_with_owner(
                    user_id=owner.id,
                    name="Owned",
                    description=None,
                )
                session.add_all(
                    [
                        GroupMember(
                            group_id=owned.group.id,
                            user_id=active_friend.id,
                            role=GroupMemberRole.MEMBER,
                            status=GroupMemberStatus.ACTIVE,
                            left_at=None,
                        ),
                        GroupMember(
                            group_id=owned.group.id,
                            user_id=left_friend.id,
                            role=GroupMemberRole.MEMBER,
                            status=GroupMemberStatus.LEFT,
                            left_at=NOW,
                        ),
                    ]
                )

                active_membership_group = await repository.create_with_owner(
                    user_id=other_owner.id,
                    name="Joined",
                    description=None,
                )
                session.add(
                    GroupMember(
                        group_id=active_membership_group.group.id,
                        user_id=owner.id,
                        role=GroupMemberRole.MEMBER,
                        status=GroupMemberStatus.ACTIVE,
                        left_at=None,
                    )
                )

                left_membership_group = await repository.create_with_owner(
                    user_id=other_owner.id,
                    name="Left",
                    description=None,
                )
                session.add(
                    GroupMember(
                        group_id=left_membership_group.group.id,
                        user_id=owner.id,
                        role=GroupMemberRole.MEMBER,
                        status=GroupMemberStatus.LEFT,
                        left_at=NOW,
                    )
                )
                await session.flush()

                await session.execute(
                    update(GroupMember)
                    .where(
                        GroupMember.user_id == owner.id,
                        GroupMember.status == GroupMemberStatus.ACTIVE,
                    )
                    .values(created_at=NOW)
                )
                await repository.commit()

                select_statements = 0

                def count_selects(
                    _conn: object,
                    _cursor: object,
                    statement: str,
                    _parameters: object,
                    _context: object,
                    _executemany: object,
                ) -> None:
                    nonlocal select_statements
                    if statement.lstrip().upper().startswith("SELECT"):
                        select_statements += 1

                event.listen(connection.sync_connection, "before_cursor_execute", count_selects)
                try:
                    first_page = await repository.list_active_groups(
                        user_id=owner.id,
                        after=None,
                        limit=1,
                    )
                finally:
                    event.remove(
                        connection.sync_connection,
                        "before_cursor_execute",
                        count_selects,
                    )

                assert select_statements == 1
                assert len(first_page) == 1
                second_page = await repository.list_active_groups(
                    user_id=owner.id,
                    after=PageCursor(
                        joined_at=first_page[-1].joined_at,
                        membership_id=first_page[-1].membership_id,
                    ),
                    limit=10,
                )
                visible_ids = [item.group.id for item in first_page + second_page]
                assert set(visible_ids) == {
                    owned.group.id,
                    active_membership_group.group.id,
                }
                assert len(visible_ids) == len(set(visible_ids))
                assert left_membership_group.group.id not in visible_ids

                detail = await repository.get_active_group(
                    group_id=owned.group.id,
                    user_id=owner.id,
                )
                assert detail is not None
                assert detail.member_count == 2

                owner_delete_target = await repository.get_active_group_for_update(
                    group_id=owned.group.id,
                    user_id=owner.id,
                )
                member_delete_target = await repository.get_active_group_for_update(
                    group_id=owned.group.id,
                    user_id=active_friend.id,
                )
                left_delete_target = await repository.get_active_group_for_update(
                    group_id=owned.group.id,
                    user_id=left_friend.id,
                )
                missing_delete_target = await repository.get_active_group_for_update(
                    group_id=owned.group.id,
                    user_id=uuid4(),
                )
                assert owner_delete_target is not None
                assert owner_delete_target.current_user_role == GroupMemberRole.OWNER
                assert member_delete_target is not None
                assert member_delete_target.current_user_role == GroupMemberRole.MEMBER
                assert left_delete_target is None
                assert missing_delete_target is None

                members = await repository.list_active_members(
                    group_id=owned.group.id,
                    after=None,
                    limit=10,
                )
                assert {member.user_id for member in members} == {owner.id, active_friend.id}
                assert {member.nickname for member in members} == {"Owner", "Active Friend"}
        finally:
            await outer_transaction.rollback()


async def test_delete_group_cascades_domain_data_but_preserves_users_and_other_groups() -> None:
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                owner = make_user(nickname="Owner")
                owner.avatar_url = "https://example.com/owner-avatar.jpg"
                member = make_user(nickname="Member")
                session.add_all([owner, member])
                await session.flush()

                repository = GroupRepository(session)
                target = await repository.create_with_owner(
                    user_id=owner.id,
                    name="Delete Target",
                    description=None,
                )
                other = await repository.create_with_owner(
                    user_id=owner.id,
                    name="Keep Target",
                    description=None,
                )
                target_member = GroupMember(
                    group_id=target.group.id,
                    user_id=member.id,
                    role=GroupMemberRole.MEMBER,
                    status=GroupMemberStatus.ACTIVE,
                    left_at=None,
                )
                session.add(target_member)

                hangout = Hangout(
                    group_id=target.group.id,
                    created_by_user_id=owner.id,
                    title="Delete Hangout",
                    description=None,
                    status=HangoutStatus.VOTING,
                    voting_deadline=None,
                    confirmed_at=None,
                    cancelled_at=None,
                )
                session.add(hangout)
                await session.flush()

                proposal = Proposal(
                    hangout_id=hangout.id,
                    submitted_by_user_id=owner.id,
                    title="Delete Proposal",
                    description=None,
                    location_text=None,
                    external_platform=None,
                    external_url=None,
                    external_data=None,
                )
                time_option = TimeOption(
                    hangout_id=hangout.id,
                    created_by_user_id=owner.id,
                    starts_at=NOW,
                    ends_at=NOW + timedelta(hours=2),
                    display_label=None,
                )
                session.add_all([proposal, time_option])
                await session.flush()

                proposal_vote = ProposalVote(
                    proposal_id=proposal.id,
                    user_id=member.id,
                    value=ProposalVoteValue.LIKE,
                )
                time_vote = TimeVote(time_option_id=time_option.id, user_id=member.id)
                event_record = Event(
                    hangout_id=hangout.id,
                    proposal_id=proposal.id,
                    time_option_id=time_option.id,
                    confirmed_by_user_id=owner.id,
                    title="Delete Event",
                    description=None,
                    location_text=None,
                    starts_at=NOW,
                    ends_at=NOW + timedelta(hours=2),
                )
                session.add_all([proposal_vote, time_vote, event_record])
                await session.flush()

                deleted_ids = {
                    Group: target.group.id,
                    GroupMember: target_member.id,
                    Hangout: hangout.id,
                    Proposal: proposal.id,
                    ProposalVote: proposal_vote.id,
                    TimeOption: time_option.id,
                    TimeVote: time_vote.id,
                    Event: event_record.id,
                }
                invite_tokens = GroupInviteTokenService(
                    secret=SECRET,
                    issuer="test-issuer",
                    audience="test-audience",
                )
                old_invite_token = invite_tokens.issue(target.group.id).value
                service = GroupService(
                    repository=repository,
                    invite_tokens=invite_tokens,
                    cursors=SignedCursorCodec(secret=SECRET),
                )

                await service.delete_group(
                    owner,
                    group_id=target.group.id,
                    confirmation_name="  Delete Target  ",
                )

                for model, record_id in deleted_ids.items():
                    count = await session.scalar(
                        select(func.count(model.id)).where(model.id == record_id)
                    )
                    assert count == 0, model.__tablename__

                persisted_users = (
                    await session.scalars(select(User).where(User.id.in_([owner.id, member.id])))
                ).all()
                assert {user.id for user in persisted_users} == {owner.id, member.id}
                persisted_owner = next(user for user in persisted_users if user.id == owner.id)
                assert persisted_owner.avatar_url == "https://example.com/owner-avatar.jpg"
                assert (
                    await session.scalar(
                        select(func.count(Group.id)).where(Group.id == other.group.id)
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        select(func.count(GroupMember.id)).where(
                            GroupMember.group_id == other.group.id,
                            GroupMember.user_id == owner.id,
                        )
                    )
                    == 1
                )

                with pytest.raises(GroupNotFoundError):
                    await service.join_group(
                        member,
                        group_id=target.group.id,
                        invite_token=old_invite_token,
                    )
                assert (
                    await session.scalar(
                        select(func.count(GroupMember.id)).where(
                            GroupMember.group_id == target.group.id
                        )
                    )
                    == 0
                )
        finally:
            await outer_transaction.rollback()


async def test_delete_group_commit_failure_rolls_back_database_delete() -> None:
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
                setup_repository = GroupRepository(session)
                created = await setup_repository.create_with_owner(
                    user_id=owner.id,
                    name="Rollback Delete",
                    description=None,
                )
                await setup_repository.commit()
                owner_id = owner.id
                group_id = created.group.id

                class FailingCommitRepository(GroupRepository):
                    async def commit(self) -> None:
                        raise RuntimeError("simulated commit failure")

                service = GroupService(
                    repository=FailingCommitRepository(session),
                    invite_tokens=GroupInviteTokenService(
                        secret=SECRET,
                        issuer="test-issuer",
                        audience="test-audience",
                    ),
                    cursors=SignedCursorCodec(secret=SECRET),
                )

                with pytest.raises(RuntimeError, match="simulated commit failure"):
                    await service.delete_group(
                        owner,
                        group_id=group_id,
                        confirmation_name="Rollback Delete",
                    )

                assert (
                    await session.scalar(select(func.count(Group.id)).where(Group.id == group_id))
                    == 1
                )
                assert (
                    await session.scalar(
                        select(func.count(GroupMember.id)).where(
                            GroupMember.group_id == group_id,
                            GroupMember.user_id == owner_id,
                        )
                    )
                    == 1
                )
        finally:
            await outer_transaction.rollback()


async def test_create_group_rolls_back_if_owner_creation_fails() -> None:
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
                await session.commit()
                attempted_group_id: UUID | None = None

                class FailingOwnerRepository(GroupRepository):
                    async def create_with_owner(self, **arguments: object):  # type: ignore[no-untyped-def]
                        nonlocal attempted_group_id
                        group = Group(
                            name=str(arguments["name"]),
                            description=None,
                            created_by_user_id=arguments["user_id"],
                        )
                        session.add(group)
                        await session.flush()
                        attempted_group_id = group.id
                        raise RuntimeError("simulated owner insert failure")

                service = GroupService(
                    repository=FailingOwnerRepository(session),
                    invite_tokens=GroupInviteTokenService(
                        secret=SECRET,
                        issuer="test-issuer",
                        audience="test-audience",
                    ),
                    cursors=SignedCursorCodec(secret=SECRET),
                )

                with pytest.raises(RuntimeError, match="simulated owner insert failure"):
                    await service.create_group(owner, name="Atomic", description=None)

                assert attempted_group_id is not None
                persisted = await session.scalar(
                    select(func.count(Group.id)).where(Group.id == attempted_group_id)
                )
                assert persisted == 0
        finally:
            await outer_transaction.rollback()


async def test_mysql_upsert_handles_concurrent_repeat_left_and_owner_join() -> None:
    owner = make_user(nickname="Owner")
    joiner = make_user(nickname="Joiner")
    group_id: UUID | None = None
    try:
        async with async_session_factory() as setup_session:
            setup_session.add_all([owner, joiner])
            await setup_session.flush()
            repository = GroupRepository(setup_session)
            created = await repository.create_with_owner(
                user_id=owner.id,
                name=f"Concurrent {uuid4().hex[:20]}",
                description=None,
            )
            group_id = created.group.id
            await repository.commit()

        async def join_once(user_id: UUID) -> GroupMember:
            async with async_session_factory() as join_session:
                repository = GroupRepository(join_session)
                membership = await repository.join_group(group_id=group_id, user_id=user_id)
                await repository.commit()
                return membership

        first, second = await asyncio.gather(join_once(joiner.id), join_once(joiner.id))
        assert first.id == second.id

        async with async_session_factory() as verification_session:
            memberships = (
                await verification_session.scalars(
                    select(GroupMember).where(
                        GroupMember.group_id == group_id,
                        GroupMember.user_id == joiner.id,
                    )
                )
            ).all()
            assert len(memberships) == 1
            membership_id = memberships[0].id

            await verification_session.execute(
                update(GroupMember)
                .where(GroupMember.id == membership_id)
                .values(status=GroupMemberStatus.LEFT, left_at=NOW)
            )
            await verification_session.commit()

        restored = await join_once(joiner.id)
        assert restored.id == membership_id
        assert restored.status == GroupMemberStatus.ACTIVE
        assert restored.role == GroupMemberRole.MEMBER
        assert restored.left_at is None

        repeated = await join_once(joiner.id)
        assert repeated.id == membership_id

        owner_membership = await join_once(owner.id)
        assert owner_membership.role == GroupMemberRole.OWNER
    finally:
        if group_id is not None:
            async with async_session_factory() as cleanup_session:
                await cleanup_session.execute(delete(Group).where(Group.id == group_id))
                await cleanup_session.execute(
                    delete(User).where(User.id.in_([owner.id, joiner.id]))
                )
                await cleanup_session.commit()
