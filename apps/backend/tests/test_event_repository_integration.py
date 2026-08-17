import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    EventSelectionConflictError,
    ProposalNotFoundError,
    TimeOptionNotFoundError,
    VoteStateConflictError,
)
from app.db.session import engine
from app.models.enums import (
    GroupMemberRole,
    GroupMemberStatus,
    HangoutStatus,
    ProposalVoteValue,
)
from app.models.event import Event
from app.models.group import Group, GroupMember
from app.models.hangout import Hangout
from app.models.proposal import Proposal
from app.models.time_option import TimeOption
from app.models.user import User
from app.repositories.event import EventRepository
from app.repositories.vote import VoteRepository
from app.services.event import EventService
from app.services.vote import VoteService

pytestmark = [
    pytest.mark.skipif(
        os.getenv("RUN_DATABASE_TESTS") != "1",
        reason="set RUN_DATABASE_TESTS=1 when a migrated MySQL test database is available",
    ),
    pytest.mark.asyncio(loop_scope="session"),
]

NOW = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)


def make_user(*, nickname: str) -> User:
    suffix = uuid4().hex
    return User(
        wechat_openid=f"event-test-openid-{suffix}",
        wechat_unionid=None,
        display_name=nickname,
        avatar_url=None,
        is_active=True,
        profile_completed=True,
        last_login_at=NOW,
    )


async def create_event_resources(
    session: AsyncSession,
) -> tuple[
    User,
    User,
    User,
    Group,
    Hangout,
    list[Proposal],
    list[TimeOption],
    Proposal,
    TimeOption,
]:
    owner = make_user(nickname="Owner")
    creator = make_user(nickname="Creator")
    member = make_user(nickname="Member")
    session.add_all([owner, creator, member])
    await session.flush()

    group = Group(name="Event Integration", description=None, created_by_user_id=owner.id)
    session.add(group)
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
                user_id=creator.id,
                role=GroupMemberRole.MEMBER,
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
        ]
    )
    hangout = Hangout(
        group_id=group.id,
        created_by_user_id=creator.id,
        title="Voting",
        description=None,
        status=HangoutStatus.VOTING,
        voting_deadline=NOW + timedelta(days=10),
        confirmed_at=None,
        cancelled_at=None,
    )
    other_hangout = Hangout(
        group_id=group.id,
        created_by_user_id=creator.id,
        title="Other Voting",
        description=None,
        status=HangoutStatus.VOTING,
        voting_deadline=None,
        confirmed_at=None,
        cancelled_at=None,
    )
    session.add_all([hangout, other_hangout])
    await session.flush()

    proposals = [
        Proposal(
            hangout_id=hangout.id,
            submitted_by_user_id=creator.id,
            title=f"Proposal {index}",
            description=f"Description {index}",
            location_text=f"Location {index}",
            external_platform=None,
            external_url=None,
            external_data=None,
        )
        for index in range(2)
    ]
    time_options = [
        TimeOption(
            hangout_id=hangout.id,
            created_by_user_id=creator.id,
            starts_at=NOW + timedelta(days=1 + index),
            ends_at=NOW + timedelta(days=1 + index, hours=2),
            display_label=f"Option {index}",
        )
        for index in range(2)
    ]
    other_proposal = Proposal(
        hangout_id=other_hangout.id,
        submitted_by_user_id=creator.id,
        title="Other Proposal",
        description=None,
        location_text=None,
        external_platform=None,
        external_url=None,
        external_data=None,
    )
    other_time_option = TimeOption(
        hangout_id=other_hangout.id,
        created_by_user_id=creator.id,
        starts_at=NOW + timedelta(days=3),
        ends_at=None,
        display_label="Other Option",
    )
    session.add_all([*proposals, *time_options, other_proposal, other_time_option])
    await session.flush()
    return (
        owner,
        creator,
        member,
        group,
        hangout,
        proposals,
        time_options,
        other_proposal,
        other_time_option,
    )


async def test_confirmation_persists_snapshot_is_idempotent_and_closes_voting() -> None:
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                (
                    _owner,
                    creator,
                    member,
                    group,
                    hangout,
                    proposals,
                    time_options,
                    _other_proposal,
                    _other_time_option,
                ) = await create_event_resources(session)
                await session.commit()
                service = EventService(
                    repository=EventRepository(session),
                    clock=lambda: NOW,
                )
                group_id = group.id
                hangout_id = hangout.id
                member_id = member.id
                selected_proposal_id = proposals[0].id
                selected_time_option_id = time_options[0].id
                other_proposal_id = proposals[1].id
                other_time_option_id = time_options[1].id

                confirmed = await service.confirm_event(
                    creator,
                    group_id=group_id,
                    hangout_id=hangout_id,
                    proposal_id=selected_proposal_id,
                    time_option_id=selected_time_option_id,
                )

                assert confirmed.title == proposals[0].title
                assert confirmed.description == proposals[0].description
                assert confirmed.location_text == proposals[0].location_text
                assert confirmed.starts_at == time_options[0].starts_at
                assert confirmed.ends_at == time_options[0].ends_at
                assert confirmed.confirmed_by_user_id == creator.id
                await session.refresh(hangout)
                assert hangout.status == HangoutStatus.CONFIRMED
                assert hangout.confirmed_at == NOW
                assert (
                    await session.scalar(
                        select(func.count(Event.id)).where(Event.hangout_id == hangout.id)
                    )
                    == 1
                )

                repeated = await service.confirm_event(
                    creator,
                    group_id=group_id,
                    hangout_id=hangout_id,
                    proposal_id=selected_proposal_id,
                    time_option_id=selected_time_option_id,
                )
                assert repeated.id == confirmed.id

                with pytest.raises(EventSelectionConflictError):
                    await service.confirm_event(
                        creator,
                        group_id=group_id,
                        hangout_id=hangout_id,
                        proposal_id=other_proposal_id,
                        time_option_id=other_time_option_id,
                    )
                assert (
                    await session.scalar(
                        select(func.count(Event.id)).where(Event.hangout_id == hangout_id)
                    )
                    == 1
                )

                member = await session.get(User, member_id)
                assert member is not None
                vote_service = VoteService(
                    repository=VoteRepository(session),
                    clock=lambda: NOW,
                )
                summary = await vote_service.read_summary(
                    member,
                    group_id=group_id,
                    hangout_id=hangout_id,
                )
                assert summary.hangout.status == HangoutStatus.CONFIRMED
                with pytest.raises(VoteStateConflictError):
                    await vote_service.set_proposal_vote(
                        member,
                        group_id=group_id,
                        hangout_id=hangout_id,
                        proposal_id=selected_proposal_id,
                        value=ProposalVoteValue.LIKE,
                    )
        finally:
            await outer_transaction.rollback()


async def test_cross_hangout_candidates_leave_no_event_or_status_change() -> None:
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                (
                    _owner,
                    creator,
                    _member,
                    group,
                    hangout,
                    proposals,
                    time_options,
                    other_proposal,
                    other_time_option,
                ) = await create_event_resources(session)
                await session.commit()
                service = EventService(
                    repository=EventRepository(session),
                    clock=lambda: NOW,
                )
                creator_id = creator.id
                group_id = group.id
                hangout_id = hangout.id
                proposal_id = proposals[0].id
                time_option_id = time_options[0].id
                other_proposal_id = other_proposal.id
                other_time_option_id = other_time_option.id

                with pytest.raises(ProposalNotFoundError):
                    await service.confirm_event(
                        creator,
                        group_id=group_id,
                        hangout_id=hangout_id,
                        proposal_id=other_proposal_id,
                        time_option_id=time_option_id,
                    )
                creator = await session.get(User, creator_id)
                assert creator is not None
                with pytest.raises(TimeOptionNotFoundError):
                    await service.confirm_event(
                        creator,
                        group_id=group_id,
                        hangout_id=hangout_id,
                        proposal_id=proposal_id,
                        time_option_id=other_time_option_id,
                    )

                hangout = await session.get(Hangout, hangout_id)
                assert hangout is not None
                assert hangout.status == HangoutStatus.VOTING
                assert hangout.confirmed_at is None
                assert (
                    await session.scalar(
                        select(func.count(Event.id)).where(Event.hangout_id == hangout_id)
                    )
                    == 0
                )
        finally:
            await outer_transaction.rollback()


async def test_commit_failure_rolls_back_event_and_hangout_status_together() -> None:
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                (
                    _owner,
                    creator,
                    _member,
                    group,
                    hangout,
                    proposals,
                    time_options,
                    _other_proposal,
                    _other_time_option,
                ) = await create_event_resources(session)
                await session.commit()

                class FailingCommitRepository(EventRepository):
                    async def commit(self) -> None:
                        raise RuntimeError("simulated commit failure")

                service = EventService(
                    repository=FailingCommitRepository(session),
                    clock=lambda: NOW,
                )
                with pytest.raises(RuntimeError, match="simulated commit failure"):
                    await service.confirm_event(
                        creator,
                        group_id=group.id,
                        hangout_id=hangout.id,
                        proposal_id=proposals[0].id,
                        time_option_id=time_options[0].id,
                    )

                await session.refresh(hangout)
                assert hangout.status == HangoutStatus.VOTING
                assert hangout.confirmed_at is None
                assert (
                    await session.scalar(
                        select(func.count(Event.id)).where(Event.hangout_id == hangout.id)
                    )
                    == 0
                )
        finally:
            await outer_transaction.rollback()


async def test_concurrent_different_confirmations_create_at_most_one_event() -> None:
    async with AsyncSession(engine, expire_on_commit=False) as setup_session:
        (
            owner,
            creator,
            member,
            group,
            hangout,
            proposals,
            time_options,
            _other_proposal,
            _other_time_option,
        ) = await create_event_resources(setup_session)
        user_ids = [owner.id, creator.id, member.id]
        await setup_session.commit()

    async def confirm(
        current_user: User,
        proposal: Proposal,
        time_option: TimeOption,
    ) -> Event:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            service = EventService(
                repository=EventRepository(session),
                clock=lambda: NOW,
            )
            return await service.confirm_event(
                current_user,
                group_id=group.id,
                hangout_id=hangout.id,
                proposal_id=proposal.id,
                time_option_id=time_option.id,
            )

    try:
        results = await asyncio.gather(
            confirm(owner, proposals[0], time_options[0]),
            confirm(creator, proposals[1], time_options[1]),
            return_exceptions=True,
        )
        assert sum(isinstance(result, Event) for result in results) == 1
        assert sum(isinstance(result, EventSelectionConflictError) for result in results) == 1

        async with AsyncSession(engine) as verification_session:
            events = list(
                (
                    await verification_session.scalars(
                        select(Event).where(Event.hangout_id == hangout.id)
                    )
                ).all()
            )
            persisted_hangout = await verification_session.get(Hangout, hangout.id)
            assert len(events) == 1
            assert persisted_hangout is not None
            assert persisted_hangout.status == HangoutStatus.CONFIRMED
            assert persisted_hangout.confirmed_at == NOW
            assert (events[0].proposal_id, events[0].time_option_id) in {
                (proposals[0].id, time_options[0].id),
                (proposals[1].id, time_options[1].id),
            }
    finally:
        async with AsyncSession(engine) as cleanup_session:
            await cleanup_session.execute(delete(Group).where(Group.id == group.id))
            await cleanup_session.execute(delete(User).where(User.id.in_(user_ids)))
            await cleanup_session.commit()
