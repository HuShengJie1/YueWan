from http import HTTPStatus


class AppError(Exception):
    """A safe application error that can be returned through the API envelope."""

    def __init__(
        self,
        *,
        status_code: int,
        code: int,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


class InvalidWeChatCodeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.UNAUTHORIZED,
            code=40101,
            message="Invalid or expired WeChat login code",
            headers={"WWW-Authenticate": "Bearer"},
        )


class InvalidAccessTokenError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.UNAUTHORIZED,
            code=40102,
            message="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )


class InactiveUserError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.FORBIDDEN,
            code=40301,
            message="User account is inactive",
        )


class WeChatLoginBlockedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.FORBIDDEN,
            code=40302,
            message="WeChat login was blocked",
        )


class WeChatServiceUnavailableError(AppError):
    def __init__(self, *, retry_after: int | None = None) -> None:
        headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
        super().__init__(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code=50301,
            message="WeChat login service is temporarily unavailable",
            headers=headers,
        )


class AuthNotConfiguredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code=50302,
            message="Authentication service is not configured",
        )


class AvatarFileTooLargeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            code=41301,
            message="Avatar file is too large",
        )


class UnsupportedAvatarTypeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            code=41501,
            message="Unsupported avatar image type",
        )


class InvalidAvatarImageError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code=42201,
            message="Invalid avatar image",
        )


class AvatarStorageUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code=50303,
            message="Avatar storage is temporarily unavailable",
        )


class GroupNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.NOT_FOUND,
            code=40410,
            message="Group not found",
        )


class GroupOwnerRequiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.FORBIDDEN,
            code=40310,
            message="Only the group owner can delete this group",
        )


class GroupStateConflictError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.CONFLICT,
            code=40910,
            message="Group state conflict",
        )


class InvalidGroupInviteTokenError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code=42210,
            message="Invalid group invite token",
        )


class ExpiredGroupInviteTokenError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code=42211,
            message="Group invite token has expired",
        )


class GroupInviteMismatchError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code=42212,
            message="Group invite token does not match this group",
        )


class InvalidGroupCursorError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code=42213,
            message="Invalid pagination cursor",
        )


class GroupConfirmationNameMismatchError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code=42214,
            message="Group confirmation name does not match",
        )
