from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import CurrentUser, get_hangout_service
from app.schemas.common import ApiErrorResponse, ApiResponse
from app.schemas.hangout import (
    HangoutCreate,
    HangoutListData,
    HangoutRead,
    HangoutUpdate,
)
from app.services.hangout import HangoutService

router = APIRouter(prefix="/groups/{group_id}/hangouts", tags=["hangouts"])
HangoutServiceDependency = Annotated[HangoutService, Depends(get_hangout_service)]
PageCursorQuery = Annotated[str | None, Query(max_length=2048)]
PageLimitQuery = Annotated[int, Query(ge=1, le=100)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[HangoutRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def create_hangout(
    group_id: UUID,
    payload: HangoutCreate,
    current_user: CurrentUser,
    service: HangoutServiceDependency,
    request: Request,
    response: Response,
) -> ApiResponse[HangoutRead]:
    hangout = await service.create_hangout(
        current_user,
        group_id=group_id,
        title=payload.title,
        description=payload.description,
        voting_deadline=payload.voting_deadline,
    )
    response.headers["Location"] = str(
        request.url_for(
            "read_hangout",
            group_id=str(group_id),
            hangout_id=str(hangout.id),
        )
    )
    return ApiResponse(data=HangoutRead.from_hangout(hangout))


@router.get(
    "",
    response_model=ApiResponse[HangoutListData],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def list_hangouts(
    group_id: UUID,
    current_user: CurrentUser,
    service: HangoutServiceDependency,
    cursor: PageCursorQuery = None,
    limit: PageLimitQuery = 20,
) -> ApiResponse[HangoutListData]:
    page = await service.list_hangouts(
        current_user,
        group_id=group_id,
        cursor=cursor,
        limit=limit,
    )
    return ApiResponse(
        data=HangoutListData(
            items=[HangoutRead.from_hangout(item) for item in page.items],
            next_cursor=page.next_cursor,
            has_more=page.has_more,
        )
    )


@router.get(
    "/{hangout_id}",
    name="read_hangout",
    response_model=ApiResponse[HangoutRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
    },
)
async def read_hangout(
    group_id: UUID,
    hangout_id: UUID,
    current_user: CurrentUser,
    service: HangoutServiceDependency,
) -> ApiResponse[HangoutRead]:
    hangout = await service.read_hangout(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
    )
    return ApiResponse(data=HangoutRead.from_hangout(hangout))


@router.put(
    "/{hangout_id}",
    response_model=ApiResponse[HangoutRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def update_hangout(
    group_id: UUID,
    hangout_id: UUID,
    payload: HangoutUpdate,
    current_user: CurrentUser,
    service: HangoutServiceDependency,
) -> ApiResponse[HangoutRead]:
    hangout = await service.update_hangout(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
        title=payload.title,
        description=payload.description,
        voting_deadline=payload.voting_deadline,
    )
    return ApiResponse(data=HangoutRead.from_hangout(hangout))


@router.put(
    "/{hangout_id}/voting",
    response_model=ApiResponse[HangoutRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def start_voting(
    group_id: UUID,
    hangout_id: UUID,
    current_user: CurrentUser,
    service: HangoutServiceDependency,
) -> ApiResponse[HangoutRead]:
    hangout = await service.start_voting(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
    )
    return ApiResponse(data=HangoutRead.from_hangout(hangout))
