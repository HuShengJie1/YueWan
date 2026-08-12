from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import CurrentUser, get_proposal_service
from app.schemas.common import ApiErrorResponse, ApiResponse
from app.schemas.proposal import (
    ProposalCreate,
    ProposalListData,
    ProposalRead,
    ProposalUpdate,
)
from app.services.proposal import ManagedProposal, ProposalService

router = APIRouter(
    prefix="/groups/{group_id}/hangouts/{hangout_id}/proposals",
    tags=["proposals"],
)
ProposalServiceDependency = Annotated[ProposalService, Depends(get_proposal_service)]
PageCursorQuery = Annotated[str | None, Query(max_length=2048)]
PageLimitQuery = Annotated[int, Query(ge=1, le=100)]


def proposal_response(item: ManagedProposal) -> ProposalRead:
    return ProposalRead.from_proposal(item.proposal, can_manage=item.can_manage)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[ProposalRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def create_proposal(
    group_id: UUID,
    hangout_id: UUID,
    payload: ProposalCreate,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
    request: Request,
    response: Response,
) -> ApiResponse[ProposalRead]:
    proposal = await service.create_proposal(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
        title=payload.title,
        description=payload.description,
        location_text=payload.location_text,
        external_platform=payload.external_platform,
        external_url=payload.external_url,
        external_data=payload.external_data,
    )
    response.headers["Location"] = str(
        request.url_for(
            "update_proposal",
            group_id=str(group_id),
            hangout_id=str(hangout_id),
            proposal_id=str(proposal.proposal.id),
        )
    )
    return ApiResponse(data=proposal_response(proposal))


@router.get(
    "",
    response_model=ApiResponse[ProposalListData],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def list_proposals(
    group_id: UUID,
    hangout_id: UUID,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
    cursor: PageCursorQuery = None,
    limit: PageLimitQuery = 20,
) -> ApiResponse[ProposalListData]:
    page = await service.list_proposals(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
        cursor=cursor,
        limit=limit,
    )
    return ApiResponse(
        data=ProposalListData(
            items=[proposal_response(item) for item in page.items],
            next_cursor=page.next_cursor,
            has_more=page.has_more,
        )
    )


@router.put(
    "/{proposal_id}",
    name="update_proposal",
    response_model=ApiResponse[ProposalRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def update_proposal(
    group_id: UUID,
    hangout_id: UUID,
    proposal_id: UUID,
    payload: ProposalUpdate,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> ApiResponse[ProposalRead]:
    proposal = await service.update_proposal(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
        proposal_id=proposal_id,
        title=payload.title,
        description=payload.description,
        location_text=payload.location_text,
        external_platform=payload.external_platform,
        external_url=payload.external_url,
        external_data=payload.external_data,
    )
    return ApiResponse(data=proposal_response(proposal))


@router.delete(
    "/{proposal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def delete_proposal(
    group_id: UUID,
    hangout_id: UUID,
    proposal_id: UUID,
    current_user: CurrentUser,
    service: ProposalServiceDependency,
) -> Response:
    await service.delete_proposal(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
        proposal_id=proposal_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
