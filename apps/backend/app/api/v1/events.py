from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_event_service
from app.schemas.common import ApiErrorResponse, ApiResponse
from app.schemas.event import EventConfirm, EventRead
from app.services.event import EventService

router = APIRouter(
    prefix="/groups/{group_id}/hangouts/{hangout_id}/event",
    tags=["events"],
)
EventServiceDependency = Annotated[EventService, Depends(get_event_service)]

ERROR_RESPONSES = {
    401: {"model": ApiErrorResponse},
    403: {"model": ApiErrorResponse},
    404: {"model": ApiErrorResponse},
    409: {"model": ApiErrorResponse},
    422: {"model": ApiErrorResponse},
}


@router.get(
    "",
    response_model=ApiResponse[EventRead],
    responses=ERROR_RESPONSES,
)
async def read_event(
    group_id: UUID,
    hangout_id: UUID,
    current_user: CurrentUser,
    service: EventServiceDependency,
) -> ApiResponse[EventRead]:
    event = await service.read_event(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
    )
    return ApiResponse(data=EventRead.from_event(event))


@router.put(
    "",
    response_model=ApiResponse[EventRead],
    responses=ERROR_RESPONSES,
)
async def confirm_event(
    group_id: UUID,
    hangout_id: UUID,
    payload: EventConfirm,
    current_user: CurrentUser,
    service: EventServiceDependency,
) -> ApiResponse[EventRead]:
    event = await service.confirm_event(
        current_user,
        group_id=group_id,
        hangout_id=hangout_id,
        proposal_id=payload.proposal_id,
        time_option_id=payload.time_option_id,
    )
    return ApiResponse(data=EventRead.from_event(event))
