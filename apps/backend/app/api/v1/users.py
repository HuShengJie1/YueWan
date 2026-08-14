from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import (
    CurrentUser,
    get_avatar_service,
    get_avatar_upload_limit,
    get_user_service,
)
from app.core.exceptions import AvatarFileTooLargeError
from app.schemas.common import ApiErrorResponse, ApiResponse
from app.schemas.user import CloudAvatarUpdate, UserRead, UserUpdate
from app.services.avatar import AvatarService
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["users"])
UserServiceDependency = Annotated[UserService, Depends(get_user_service)]
AvatarServiceDependency = Annotated[AvatarService, Depends(get_avatar_service)]
AvatarUploadLimit = Annotated[int, Depends(get_avatar_upload_limit)]


@router.get(
    "/me",
    response_model=ApiResponse[UserRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
    },
)
async def read_current_user(current_user: CurrentUser) -> ApiResponse[UserRead]:
    return ApiResponse(data=UserRead.from_user(current_user))


@router.put(
    "/me",
    response_model=ApiResponse[UserRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def update_current_user(
    payload: UserUpdate,
    current_user: CurrentUser,
    service: UserServiceDependency,
) -> ApiResponse[UserRead]:
    user = await service.update_profile(current_user, nickname=payload.nickname)
    return ApiResponse(data=UserRead.from_user(user))


@router.post(
    "/me/avatar",
    response_model=ApiResponse[UserRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        413: {"model": ApiErrorResponse},
        415: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
async def upload_current_user_avatar(
    file: Annotated[UploadFile, File(description="JPEG, PNG, or WebP avatar image")],
    current_user: CurrentUser,
    service: AvatarServiceDependency,
    max_upload_bytes: AvatarUploadLimit,
) -> ApiResponse[UserRead]:
    try:
        content = await file.read(max_upload_bytes + 1)
    finally:
        await file.close()
    if len(content) > max_upload_bytes:
        raise AvatarFileTooLargeError

    user = await service.update_avatar(current_user, content=content)
    return ApiResponse(data=UserRead.from_user(user))


@router.put(
    "/me/avatar",
    response_model=ApiResponse[UserRead],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        413: {"model": ApiErrorResponse},
        415: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
async def update_current_user_avatar_from_cloud(
    payload: CloudAvatarUpdate,
    current_user: CurrentUser,
    service: AvatarServiceDependency,
) -> ApiResponse[UserRead]:
    user = await service.update_avatar_from_cloud(current_user, file_id=payload.file_id)
    return ApiResponse(data=UserRead.from_user(user))
