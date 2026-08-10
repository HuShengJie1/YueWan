from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import CurrentUser, get_group_service
from app.repositories.group import GroupSummary
from app.schemas.common import ApiErrorResponse, ApiResponse
from app.schemas.group import (
    DeleteGroupRequest,
    GroupCreate,
    GroupInviteTokenRead,
    GroupListData,
    GroupMemberListData,
    GroupMemberRead,
    GroupRead,
    JoinGroupRequest,
)
from app.services.group import GroupService

router = APIRouter(prefix="/groups", tags=["groups"])
GroupServiceDependency = Annotated[GroupService, Depends(get_group_service)]
PageCursorQuery = Annotated[str | None, Query(max_length=2048)]
PageLimitQuery = Annotated[int, Query(ge=1, le=100)]


def group_response(summary: GroupSummary) -> GroupRead:
    return GroupRead.from_group(
        summary.group,
        current_user_role=summary.current_user_role,
        member_count=summary.member_count,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[GroupRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def create_group(
    payload: GroupCreate,
    current_user: CurrentUser,
    service: GroupServiceDependency,
    request: Request,
    response: Response,
) -> ApiResponse[GroupRead]:
    group = await service.create_group(
        current_user,
        name=payload.name,
        description=payload.description,
    )
    response.headers["Location"] = str(request.url_for("read_group", group_id=str(group.group.id)))
    return ApiResponse(data=group_response(group))


@router.get(
    "",
    response_model=ApiResponse[GroupListData],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def list_groups(
    current_user: CurrentUser,
    service: GroupServiceDependency,
    cursor: PageCursorQuery = None,
    limit: PageLimitQuery = 20,
) -> ApiResponse[GroupListData]:
    page = await service.list_groups(current_user, cursor=cursor, limit=limit)
    return ApiResponse(
        data=GroupListData(
            items=[group_response(item) for item in page.items],
            next_cursor=page.next_cursor,
            has_more=page.has_more,
        )
    )


@router.get(
    "/{group_id}",
    name="read_group",
    response_model=ApiResponse[GroupRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
    },
)
async def read_group(
    group_id: UUID,
    current_user: CurrentUser,
    service: GroupServiceDependency,
) -> ApiResponse[GroupRead]:
    group = await service.read_group(current_user, group_id=group_id)
    return ApiResponse(data=group_response(group))


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def delete_group(
    group_id: UUID,
    payload: DeleteGroupRequest,
    current_user: CurrentUser,
    service: GroupServiceDependency,
) -> Response:
    await service.delete_group(
        current_user,
        group_id=group_id,
        confirmation_name=payload.confirmation_name,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{group_id}/members",
    response_model=ApiResponse[GroupMemberListData],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def list_group_members(
    group_id: UUID,
    current_user: CurrentUser,
    service: GroupServiceDependency,
    cursor: PageCursorQuery = None,
    limit: PageLimitQuery = 20,
) -> ApiResponse[GroupMemberListData]:
    page = await service.list_members(
        current_user,
        group_id=group_id,
        cursor=cursor,
        limit=limit,
    )
    return ApiResponse(
        data=GroupMemberListData(
            items=[
                GroupMemberRead(
                    user_id=item.user_id,
                    nickname=item.nickname,
                    avatar_url=item.avatar_url,
                    role=item.role,
                    joined_at=item.joined_at,
                )
                for item in page.items
            ],
            next_cursor=page.next_cursor,
            has_more=page.has_more,
        )
    )


@router.post(
    "/{group_id}/invite-tokens",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[GroupInviteTokenRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
    },
)
async def create_group_invite_token(
    group_id: UUID,
    current_user: CurrentUser,
    service: GroupServiceDependency,
) -> ApiResponse[GroupInviteTokenRead]:
    token = await service.create_invite_token(current_user, group_id=group_id)
    return ApiResponse(
        data=GroupInviteTokenRead(
            invite_token=token.value,
            expires_at=token.expires_at,
        )
    )


@router.put(
    "/{group_id}/members/me",
    response_model=ApiResponse[GroupRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def join_group(
    group_id: UUID,
    payload: JoinGroupRequest,
    current_user: CurrentUser,
    service: GroupServiceDependency,
) -> ApiResponse[GroupRead]:
    group = await service.join_group(
        current_user,
        group_id=group_id,
        invite_token=payload.invite_token,
    )
    return ApiResponse(data=group_response(group))
