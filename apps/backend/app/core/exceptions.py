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


class HangoutNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.NOT_FOUND,
            code=40420,
            message="Hangout not found",
        )


class HangoutEditForbiddenError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.FORBIDDEN,
            code=40320,
            message="Current member cannot edit this hangout",
        )


class HangoutStateConflictError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.CONFLICT,
            code=40920,
            message="Hangout state does not allow this operation",
        )


class HangoutVotingForbiddenError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.FORBIDDEN,
            code=40321,
            message="Current member cannot start voting for this hangout",
        )


class HangoutProposalRequiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.CONFLICT,
            code=40921,
            message="At least one proposal is required to start voting",
        )


class HangoutTimeOptionRequiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.CONFLICT,
            code=40922,
            message="At least one time option is required to start voting",
        )


class HangoutVotingDeadlineElapsedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.CONFLICT,
            code=40923,
            message="Voting deadline has already elapsed",
        )


class ProposalManageForbiddenError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.FORBIDDEN,
            code=40330,
            message="Current member cannot manage this proposal",
        )


class ProposalNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.NOT_FOUND,
            code=40430,
            message="Proposal not found",
        )


class ProposalStateConflictError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.CONFLICT,
            code=40930,
            message="Hangout state does not allow proposal changes",
        )


class TimeOptionManageForbiddenError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.FORBIDDEN,
            code=40340,
            message="Current member cannot manage this time option",
        )


class TimeOptionNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.NOT_FOUND,
            code=40440,
            message="Time option not found",
        )


class TimeOptionStateConflictError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.CONFLICT,
            code=40940,
            message="Hangout state does not allow time option changes",
        )


class InvalidTimeOptionError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code=40001,
            message="Invalid request",
        )


class VoteStateConflictError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.CONFLICT,
            code=40950,
            message="Hangout is not open for voting",
        )


class DuplicateTimeVoteSelectionError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code=42250,
            message="Time option IDs must be unique",
        )


class EventConfirmForbiddenError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.FORBIDDEN,
            code=40350,
            message="Current member cannot confirm this event",
        )


class EventNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.NOT_FOUND,
            code=40450,
            message="Event not found",
        )


class EventStateConflictError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.CONFLICT,
            code=40960,
            message="Hangout state does not allow event confirmation",
        )


class EventSelectionConflictError(AppError):
    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.CONFLICT,
            code=40961,
            message="Event was already confirmed with a different selection",
        )
