import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.group_security import ProposalPageCursor, SignedCursorCodec, TimeOptionPageCursor
from app.db.session import engine
from app.models.enums import GroupMemberRole, GroupMemberStatus, HangoutStatus
from app.models.group import Group, GroupMember
from app.models.hangout import Hangout
from app.models.proposal import Proposal
from app.models.time_option import TimeOption
from app.models.user import User
from app.repositories.proposal import ProposalRepository
from app.repositories.time_option import TimeOptionRepository
from app.services.proposal import ProposalService
from app.services.time_option import TimeOptionService

pytestmark = [
    pytest.mark.skipif(
        os.getenv("RUN_DATABASE_TESTS") != "1",
        reason="set RUN_DATABASE_TESTS=1 when a migrated MySQL test database is available",
    ),
    pytest.mark.asyncio(loop_scope="session"),
]

NOW = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
STARTS_AT = NOW + timedelta(days=4)
SECRET = "test-secret-that-is-at-least-32-bytes-long"


def make_user(*, nickname: str) -> User:
    suffix = uuid4().hex
    return User(
        wechat_openid=f"candidate-test-openid-{suffix}",
        wechat_unionid=None,
        display_name=nickname,
        avatar_url=None,
        is_active=True,
        profile_completed=True,
        last_login_at=NOW,
    )


async def create_group_context(session: AsyncSession):  # type: ignore[no-untyped-def]
    owner = make_user(nickname="Owner")
    member = make_user(nickname="Member")
    left_member = make_user(nickname="Left")
    session.add_all([owner, member, left_member])
    await session.flush()
    group = Group(name="Candidates", description=None, created_by_user_id=owner.id)
    other_group = Group(name="Other", description=None, created_by_user_id=owner.id)
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
    hangout = Hangout(
        group_id=group.id,
        created_by_user_id=owner.id,
        title="Draft",
        description=None,
        status=HangoutStatus.DRAFT,
        voting_deadline=None,
        confirmed_at=None,
        cancelled_at=None,
    )
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
    session.add_all([hangout, other_hangout])
    await session.flush()
    return owner, member, left_member, group, hangout, other_hangout


async def test_candidate_repositories_filter_membership_scope_and_page_stably() -> None:
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                (
                    owner,
                    member,
                    left_member,
                    group,
                    hangout,
                    other_hangout,
                ) = await create_group_context(session)
                proposals = [
                    Proposal(
                        hangout_id=hangout.id,
                        submitted_by_user_id=member.id,
                        title=f"Proposal {number}",
                        description=None,
                        location_text=None,
                        external_platform=None,
                        external_url=None,
                        external_data=None,
                    )
                    for number in range(2)
                ]
                other_proposal = Proposal(
                    hangout_id=other_hangout.id,
                    submitted_by_user_id=owner.id,
                    title="Other proposal",
                    description=None,
                    location_text=None,
                    external_platform=None,
                    external_url=None,
                    external_data=None,
                )
                time_options = [
                    TimeOption(
                        hangout_id=hangout.id,
                        created_by_user_id=member.id,
                        starts_at=STARTS_AT,
                        ends_at=None,
                        display_label=f"Option {number}",
                    )
                    for number in range(2)
                ]
                other_time_option = TimeOption(
                    hangout_id=other_hangout.id,
                    created_by_user_id=owner.id,
                    starts_at=STARTS_AT,
                    ends_at=None,
                    display_label="Other option",
                )
                session.add_all([*proposals, other_proposal, *time_options, other_time_option])
                await session.flush()
                await session.execute(
                    update(Proposal)
                    .where(Proposal.id.in_([item.id for item in proposals]))
                    .values(created_at=NOW)
                )
                await session.commit()

                proposal_repository = ProposalRepository(session)
                time_repository = TimeOptionRepository(session)
                assert await proposal_repository.get_active_membership(
                    group_id=group.id,
                    user_id=member.id,
                )
                assert (
                    await proposal_repository.get_active_membership(
                        group_id=group.id,
                        user_id=left_member.id,
                    )
                    is None
                )

                first_proposals = await proposal_repository.list_in_hangout(
                    hangout_id=hangout.id,
                    after=None,
                    limit=1,
                )
                second_proposals = await proposal_repository.list_in_hangout(
                    hangout_id=hangout.id,
                    after=ProposalPageCursor(
                        created_at=first_proposals[-1].created_at,
                        proposal_id=first_proposals[-1].id,
                    ),
                    limit=2,
                )
                assert [item.id for item in first_proposals + second_proposals] == sorted(
                    [item.id for item in proposals],
                    reverse=True,
                )
                assert other_proposal.id not in {
                    item.id for item in first_proposals + second_proposals
                }

                first_times = await time_repository.list_in_hangout(
                    hangout_id=hangout.id,
                    after=None,
                    limit=1,
                )
                second_times = await time_repository.list_in_hangout(
                    hangout_id=hangout.id,
                    after=TimeOptionPageCursor(
                        starts_at=first_times[-1].starts_at,
                        time_option_id=first_times[-1].id,
                    ),
                    limit=2,
                )
                assert [item.id for item in first_times + second_times] == sorted(
                    [item.id for item in time_options]
                )
                assert other_time_option.id not in {item.id for item in first_times + second_times}
        finally:
            await outer_transaction.rollback()


async def test_candidate_services_commit_and_failed_deletes_roll_back() -> None:
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                owner, _member, _left, group, hangout, _other = await create_group_context(session)
                await session.commit()
                cursors = SignedCursorCodec(secret=SECRET)
                proposal_service = ProposalService(
                    repository=ProposalRepository(session),
                    cursors=cursors,
                )
                time_service = TimeOptionService(
                    repository=TimeOptionRepository(session),
                    cursors=cursors,
                    clock=lambda: NOW,
                )
                proposal = await proposal_service.create_proposal(
                    owner,
                    group_id=group.id,
                    hangout_id=hangout.id,
                    title="Committed proposal",
                    description=None,
                    location_text=None,
                    external_platform=None,
                    external_url=None,
                    external_data=None,
                )
                time_option = await time_service.create_time_option(
                    owner,
                    group_id=group.id,
                    hangout_id=hangout.id,
                    starts_at=STARTS_AT,
                    ends_at=None,
                    display_label=None,
                )
                assert (
                    await session.scalar(
                        select(func.count(Proposal.id)).where(Proposal.id == proposal.proposal.id)
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        select(func.count(TimeOption.id)).where(
                            TimeOption.id == time_option.time_option.id
                        )
                    )
                    == 1
                )
                owner_id = owner.id
                group_id = group.id
                hangout_id = hangout.id
                proposal_id = proposal.proposal.id
                time_option_id = time_option.time_option.id

                class FailingProposalRepository(ProposalRepository):
                    async def commit(self) -> None:
                        raise RuntimeError("simulated proposal commit failure")

                with pytest.raises(RuntimeError, match="simulated proposal commit failure"):
                    await ProposalService(
                        repository=FailingProposalRepository(session),
                        cursors=cursors,
                    ).delete_proposal(
                        owner,
                        group_id=group_id,
                        hangout_id=hangout_id,
                        proposal_id=proposal_id,
                    )
                assert (
                    await session.scalar(
                        select(func.count(Proposal.id)).where(Proposal.id == proposal_id)
                    )
                    == 1
                )
                owner = await session.get(User, owner_id)
                assert owner is not None

                class FailingTimeOptionRepository(TimeOptionRepository):
                    async def commit(self) -> None:
                        raise RuntimeError("simulated time option commit failure")

                with pytest.raises(RuntimeError, match="simulated time option commit failure"):
                    await TimeOptionService(
                        repository=FailingTimeOptionRepository(session),
                        cursors=cursors,
                        clock=lambda: NOW,
                    ).delete_time_option(
                        owner,
                        group_id=group_id,
                        hangout_id=hangout_id,
                        time_option_id=time_option_id,
                    )
                assert (
                    await session.scalar(
                        select(func.count(TimeOption.id)).where(TimeOption.id == time_option_id)
                    )
                    == 1
                )
        finally:
            await outer_transaction.rollback()
