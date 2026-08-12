from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import CurrentUser, get_time_option_service
from app.schemas.common import ApiErrorResponse, ApiResponse
from app.schemas.time_option import (
    TimeOptionCreate,
    TimeOptionListData,
    TimeOptionRead,
    TimeOptionUpdate,
)
from app.services.time_option import ManagedTimeOption, TimeOptionService

router = APIRouter(
    prefix="/groups/{group_id}/hangouts/{hangout_id}/time-options",
    tags=["time-options"],
)
TimeOptionServiceDependency = Annotated[TimeOptionService, Depends(get_time_option_service)]
PageCursorQuery = Annotated[str | None, Query(max_length=2048)]
PageLimitQuery = Annotated[int, Query(ge=1, le=100)]


def time_option_response(item: ManagedTimeOption) -> TimeOptionRead:
    return TimeOptionRead.from_time_option(item.time_option, can_manage=item.can_manage)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TimeOptionRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def create_time_option(
    group_id: UUID,
    hangout_id: UUID,
    payload: TimeOptionCreate,
    current_user: CurrentUser,
    service: TimeOptionServiceDependency,
    request: Request,
    response: Response,
) -> ApiResponse[TimeOptionRead]:
    time_option = await service.create_time_option(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        display_label=payload.display_label,
    )
    response.headers["Location"] = str(
        request.url_for(
            "update_time_option",
            group_id=str(group_id),
            hangout_id=str(hangout_id),
            time_option_id=str(time_option.time_option.id),
        )
    )
    return ApiResponse(data=time_option_response(time_option))


@router.get(
    "",
    response_model=ApiResponse[TimeOptionListData],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def list_time_options(
    group_id: UUID,
    hangout_id: UUID,
    current_user: CurrentUser,
    service: TimeOptionServiceDependency,
    cursor: PageCursorQuery = None,
    limit: PageLimitQuery = 20,
) -> ApiResponse[TimeOptionListData]:
    page = await service.list_time_options(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
        cursor=cursor,
        limit=limit,
    )
    return ApiResponse(
        data=TimeOptionListData(
            items=[time_option_response(item) for item in page.items],
            next_cursor=page.next_cursor,
            has_more=page.has_more,
        )
    )


@router.put(
    "/{time_option_id}",
    name="update_time_option",
    response_model=ApiResponse[TimeOptionRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def update_time_option(
    group_id: UUID,
    hangout_id: UUID,
    time_option_id: UUID,
    payload: TimeOptionUpdate,
    current_user: CurrentUser,
    service: TimeOptionServiceDependency,
) -> ApiResponse[TimeOptionRead]:
    time_option = await service.update_time_option(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
        time_option_id=time_option_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        display_label=payload.display_label,
    )
    return ApiResponse(data=time_option_response(time_option))


@router.delete(
    "/{time_option_id}",
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
async def delete_time_option(
    group_id: UUID,
    hangout_id: UUID,
    time_option_id: UUID,
    current_user: CurrentUser,
    service: TimeOptionServiceDependency,
) -> Response:
    await service.delete_time_option(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
        time_option_id=time_option_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
