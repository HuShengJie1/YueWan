import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import TimeOptionNotFoundError
from app.db.session import engine
from app.models.enums import (
    GroupMemberRole,
    GroupMemberStatus,
    HangoutStatus,
    ProposalVoteValue,
)
from app.models.group import Group, GroupMember
from app.models.hangout import Hangout
from app.models.proposal import Proposal, ProposalVote
from app.models.time_option import TimeOption, TimeVote
from app.models.user import User
from app.repositories.vote import VoteRepository
from app.services.vote import VoteService

pytestmark = [
    pytest.mark.skipif(
        os.getenv("RUN_DATABASE_TESTS") != "1",
        reason="set RUN_DATABASE_TESTS=1 when a migrated PostgreSQL test database is available",
    ),
    pytest.mark.asyncio(loop_scope="session"),
]

NOW = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)


def make_user(*, nickname: str) -> User:
    suffix = uuid4().hex
    return User(
        wechat_openid=f"vote-test-openid-{suffix}",
        wechat_unionid=None,
        display_name=nickname,
        avatar_url=None,
        is_active=True,
        profile_completed=True,
        last_login_at=NOW,
    )


async def create_voting_resources(
    session: AsyncSession,
) -> tuple[User, User, Group, Hangout, Proposal, list[TimeOption], TimeOption]:
    owner = make_user(nickname="Owner")
    member = make_user(nickname="Member")
    session.add_all([owner, member])
    await session.flush()
    group = Group(name="Vote Integration", description=None, created_by_user_id=owner.id)
    other_group = Group(name="Other Vote Group", description=None, created_by_user_id=owner.id)
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
        ]
    )
    hangout = Hangout(
        group_id=group.id,
        created_by_user_id=owner.id,
        title="Voting",
        description=None,
        status=HangoutStatus.VOTING,
        voting_deadline=NOW + timedelta(days=10),
        confirmed_at=None,
        cancelled_at=None,
    )
    other_hangout = Hangout(
        group_id=other_group.id,
        created_by_user_id=owner.id,
        title="Other",
        description=None,
        status=HangoutStatus.VOTING,
        voting_deadline=None,
        confirmed_at=None,
        cancelled_at=None,
    )
    session.add_all([hangout, other_hangout])
    await session.flush()
    proposal = Proposal(
        hangout_id=hangout.id,
        submitted_by_user_id=owner.id,
        title="Board games",
        description=None,
        location_text=None,
        external_platform=None,
        external_url=None,
        external_data=None,
    )
    time_options = [
        TimeOption(
            hangout_id=hangout.id,
            created_by_user_id=owner.id,
            starts_at=NOW + timedelta(days=1 + index),
            ends_at=None,
            display_label=f"Option {index}",
        )
        for index in range(2)
    ]
    other_time_option = TimeOption(
        hangout_id=other_hangout.id,
        created_by_user_id=owner.id,
        starts_at=NOW + timedelta(days=3),
        ends_at=None,
        display_label="Other option",
    )
    session.add_all([proposal, *time_options, other_time_option])
    await session.flush()
    return owner, member, group, hangout, proposal, time_options, other_time_option


async def test_repository_upsert_replace_and_batch_aggregates_without_n_plus_one() -> None:
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
                    _group,
                    hangout,
                    proposal,
                    time_options,
                    _other,
                ) = await create_voting_resources(session)
                repository = VoteRepository(session)
                await repository.upsert_proposal_vote(
                    proposal_id=proposal.id,
                    user_id=owner.id,
                    value=ProposalVoteValue.LIKE,
                )
                await repository.upsert_proposal_vote(
                    proposal_id=proposal.id,
                    user_id=member.id,
                    value=ProposalVoteValue.OK,
                )
                await repository.upsert_proposal_vote(
                    proposal_id=proposal.id,
                    user_id=owner.id,
                    value=ProposalVoteValue.DISLIKE,
                )
                await repository.replace_time_votes(
                    hangout_id=hangout.id,
                    user_id=owner.id,
                    time_option_ids={item.id for item in time_options},
                )
                await repository.replace_time_votes(
                    hangout_id=hangout.id,
                    user_id=member.id,
                    time_option_ids={time_options[0].id},
                )
                await repository.commit()

                assert (
                    await session.scalar(
                        select(func.count(ProposalVote.id)).where(
                            ProposalVote.proposal_id == proposal.id,
                            ProposalVote.user_id == owner.id,
                        )
                    )
                    == 1
                )

                statements: list[str] = []

                def record_statement(
                    _connection: object,
                    _cursor: object,
                    statement: str,
                    _parameters: object,
                    _context: object,
                    _executemany: object,
                ) -> None:
                    statements.append(statement)

                event.listen(connection.sync_connection, "before_cursor_execute", record_statement)
                try:
                    proposal_summaries = await repository.list_proposal_summaries(
                        hangout_id=hangout.id,
                        current_user_id=owner.id,
                    )
                    time_summaries = await repository.list_time_summaries(
                        hangout_id=hangout.id,
                        current_user_id=owner.id,
                    )
                finally:
                    event.remove(
                        connection.sync_connection,
                        "before_cursor_execute",
                        record_statement,
                    )

                assert len(statements) == 2
                assert proposal_summaries[0].like_count == 0
                assert proposal_summaries[0].ok_count == 1
                assert proposal_summaries[0].dislike_count == 1
                assert proposal_summaries[0].current_user_vote == ProposalVoteValue.DISLIKE
                assert [item.availability_count for item in time_summaries] == [2, 1]
                assert all(item.current_user_selected for item in time_summaries)

                await repository.replace_time_votes(
                    hangout_id=hangout.id,
                    user_id=owner.id,
                    time_option_ids=set(),
                )
                await repository.commit()
                assert (
                    await session.scalar(
                        select(func.count(TimeVote.id)).where(TimeVote.user_id == owner.id)
                    )
                    == 0
                )
        finally:
            await outer_transaction.rollback()


async def test_time_vote_cross_hangout_validation_preserves_committed_selection() -> None:
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
                    member,
                    group,
                    hangout,
                    _proposal,
                    time_options,
                    other_time_option,
                ) = await create_voting_resources(session)
                service = VoteService(
                    repository=VoteRepository(session),
                    clock=lambda: NOW,
                )
                await service.replace_time_votes(
                    member,
                    group_id=group.id,
                    hangout_id=hangout.id,
                    time_option_ids=[time_options[0].id],
                )
                member_id = member.id
                expected_time_option_id = time_options[0].id
                replacement_time_option_id = time_options[1].id
                cross_hangout_time_option_id = other_time_option.id

                with pytest.raises(TimeOptionNotFoundError):
                    await service.replace_time_votes(
                        member,
                        group_id=group.id,
                        hangout_id=hangout.id,
                        time_option_ids=[
                            replacement_time_option_id,
                            cross_hangout_time_option_id,
                        ],
                    )

                selected_ids = set(
                    (
                        await session.scalars(
                            select(TimeVote.time_option_id).where(TimeVote.user_id == member_id)
                        )
                    ).all()
                )
                assert selected_ids == {expected_time_option_id}
        finally:
            await outer_transaction.rollback()


async def test_concurrent_proposal_puts_keep_one_unique_vote() -> None:
    async with AsyncSession(engine, expire_on_commit=False) as setup_session:
        owner, member, group, hangout, proposal, _times, _other = await create_voting_resources(
            setup_session
        )
        user_ids = [owner.id, member.id]
        await setup_session.commit()

    async def write_vote(value: ProposalVoteValue) -> None:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            service = VoteService(repository=VoteRepository(session), clock=lambda: NOW)
            await service.set_proposal_vote(
                member,
                group_id=group.id,
                hangout_id=hangout.id,
                proposal_id=proposal.id,
                value=value,
            )

    try:
        await asyncio.gather(
            write_vote(ProposalVoteValue.LIKE),
            write_vote(ProposalVoteValue.DISLIKE),
        )
        async with AsyncSession(engine) as verification_session:
            votes = list(
                (
                    await verification_session.scalars(
                        select(ProposalVote).where(
                            ProposalVote.proposal_id == proposal.id,
                            ProposalVote.user_id == member.id,
                        )
                    )
                ).all()
            )
            assert len(votes) == 1
            assert votes[0].value in {ProposalVoteValue.LIKE, ProposalVoteValue.DISLIKE}
    finally:
        async with AsyncSession(engine) as cleanup_session:
            await cleanup_session.execute(delete(Group).where(Group.created_by_user_id == owner.id))
            await cleanup_session.execute(delete(User).where(User.id.in_(user_ids)))
            await cleanup_session.commit()
