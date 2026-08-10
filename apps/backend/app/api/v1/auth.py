from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_auth_service
from app.schemas.auth import LoginData, WeChatLoginRequest
from app.schemas.common import ApiErrorResponse, ApiResponse
from app.schemas.user import UserRead
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


@router.post(
    "/wechat/login",
    response_model=ApiResponse[LoginData],
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
async def wechat_login(
    payload: WeChatLoginRequest,
    service: AuthServiceDependency,
) -> ApiResponse[LoginData]:
    result = await service.login_with_wechat(payload.code)
    return ApiResponse(
        data=LoginData(
            access_token=result.access_token,
            expires_in=result.expires_in,
            user=UserRead.from_user(result.user),
        )
    )
