from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_vote_service
from app.schemas.common import ApiErrorResponse, ApiResponse
from app.schemas.vote import (
    ProposalVoteWrite,
    ProposalVotingRead,
    TimeVoteListData,
    TimeVoteReplace,
    TimeVotingRead,
    VotingSummaryRead,
)
from app.services.vote import VoteService

router = APIRouter(
    prefix="/groups/{group_id}/hangouts/{hangout_id}",
    tags=["votes"],
)
VoteServiceDependency = Annotated[VoteService, Depends(get_vote_service)]

ERROR_RESPONSES = {
    401: {"model": ApiErrorResponse},
    404: {"model": ApiErrorResponse},
    409: {"model": ApiErrorResponse},
    422: {"model": ApiErrorResponse},
}


@router.get(
    "/votes",
    response_model=ApiResponse[VotingSummaryRead],
    responses=ERROR_RESPONSES,
)
async def read_voting_summary(
    group_id: UUID,
    hangout_id: UUID,
    current_user: CurrentUser,
    service: VoteServiceDependency,
) -> ApiResponse[VotingSummaryRead]:
    summary = await service.read_summary(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
    )
    return ApiResponse(data=VotingSummaryRead.from_summary(summary))


@router.put(
    "/proposals/{proposal_id}/vote",
    response_model=ApiResponse[ProposalVotingRead],
    responses=ERROR_RESPONSES,
)
async def set_proposal_vote(
    group_id: UUID,
    hangout_id: UUID,
    proposal_id: UUID,
    payload: ProposalVoteWrite,
    current_user: CurrentUser,
    service: VoteServiceDependency,
) -> ApiResponse[ProposalVotingRead]:
    summary = await service.set_proposal_vote(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
        proposal_id=proposal_id,
        value=payload.value,
    )
    return ApiResponse(data=ProposalVotingRead.from_summary(summary))


@router.delete(
    "/proposals/{proposal_id}/vote",
    response_model=ApiResponse[ProposalVotingRead],
    responses=ERROR_RESPONSES,
)
async def delete_proposal_vote(
    group_id: UUID,
    hangout_id: UUID,
    proposal_id: UUID,
    current_user: CurrentUser,
    service: VoteServiceDependency,
) -> ApiResponse[ProposalVotingRead]:
    summary = await service.delete_proposal_vote(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
        proposal_id=proposal_id,
    )
    return ApiResponse(data=ProposalVotingRead.from_summary(summary))


@router.put(
    "/time-votes/me",
    response_model=ApiResponse[TimeVoteListData],
    responses=ERROR_RESPONSES,
)
async def replace_time_votes(
    group_id: UUID,
    hangout_id: UUID,
    payload: TimeVoteReplace,
    current_user: CurrentUser,
    service: VoteServiceDependency,
) -> ApiResponse[TimeVoteListData]:
    summaries = await service.replace_time_votes(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
        time_option_ids=payload.time_option_ids,
    )
    return ApiResponse(
        data=TimeVoteListData(
            time_options=[TimeVotingRead.from_summary(item) for item in summaries]
        )
    )
