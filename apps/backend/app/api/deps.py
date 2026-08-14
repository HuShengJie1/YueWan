import logging
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AuthNotConfiguredError,
    AvatarStorageUnavailableError,
    InactiveUserError,
    InvalidAccessTokenError,
)
from app.core.group_security import GroupInviteTokenService, SignedCursorCodec
from app.core.security import AccessTokenService
from app.db.session import get_db_session
from app.integrations.storage.cloudbase import (
    CloudBaseAvatarStorage,
    CloudBaseRequestCredentials,
)
from app.integrations.storage.local import LocalAvatarStorage
from app.integrations.wechat.client import WeChatClient
from app.models.user import User
from app.repositories.event import EventRepository
from app.repositories.group import GroupRepository
from app.repositories.hangout import HangoutRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.time_option import TimeOptionRepository
from app.repositories.user import UserRepository
from app.repositories.vote import VoteRepository
from app.services.auth import AuthService
from app.services.avatar import AvatarImageProcessor, AvatarService
from app.services.event import EventService
from app.services.group import GroupService
from app.services.hangout import HangoutService
from app.services.proposal import ProposalService
from app.services.time_option import TimeOptionService
from app.services.user import UserService
from app.services.vote import VoteService

logger = logging.getLogger(__name__)
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def build_access_token_service(settings: Settings) -> AccessTokenService:
    if settings.jwt_secret is None:
        raise AuthNotConfiguredError
    secret = settings.jwt_secret.get_secret_value()
    if not secret:
        raise AuthNotConfiguredError

    try:
        return AccessTokenService(
            secret=secret,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            ttl_seconds=settings.access_token_ttl_seconds,
        )
    except ValueError as exc:
        raise AuthNotConfiguredError from exc


def get_auth_service(
    session: DbSession,
    settings: SettingsDependency,
) -> AuthService:
    if not settings.wechat_app_id or settings.wechat_app_secret is None:
        raise AuthNotConfiguredError
    app_secret = settings.wechat_app_secret.get_secret_value()
    if not app_secret:
        raise AuthNotConfiguredError

    return AuthService(
        user_repository=UserRepository(session),
        wechat_client=WeChatClient(
            app_id=settings.wechat_app_id,
            app_secret=app_secret,
        ),
        token_service=build_access_token_service(settings),
    )


def get_user_service(session: DbSession) -> UserService:
    return UserService(UserRepository(session))


def get_group_service(
    session: DbSession,
    settings: SettingsDependency,
) -> GroupService:
    if settings.jwt_secret is None:
        raise AuthNotConfiguredError
    secret = settings.jwt_secret.get_secret_value()
    if not secret:
        raise AuthNotConfiguredError
    try:
        return GroupService(
            repository=GroupRepository(session),
            invite_tokens=GroupInviteTokenService(
                secret=secret,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
            ),
            cursors=SignedCursorCodec(secret=secret),
        )
    except ValueError as exc:
        raise AuthNotConfiguredError from exc


def get_hangout_service(
    session: DbSession,
    settings: SettingsDependency,
) -> HangoutService:
    if settings.jwt_secret is None:
        raise AuthNotConfiguredError
    secret = settings.jwt_secret.get_secret_value()
    if not secret:
        raise AuthNotConfiguredError
    try:
        return HangoutService(
            repository=HangoutRepository(session),
            cursors=SignedCursorCodec(secret=secret),
        )
    except ValueError as exc:
        raise AuthNotConfiguredError from exc


def get_proposal_service(
    session: DbSession,
    settings: SettingsDependency,
) -> ProposalService:
    if settings.jwt_secret is None:
        raise AuthNotConfiguredError
    secret = settings.jwt_secret.get_secret_value()
    if not secret:
        raise AuthNotConfiguredError
    try:
        return ProposalService(
            repository=ProposalRepository(session),
            cursors=SignedCursorCodec(secret=secret),
        )
    except ValueError as exc:
        raise AuthNotConfiguredError from exc


def get_time_option_service(
    session: DbSession,
    settings: SettingsDependency,
) -> TimeOptionService:
    if settings.jwt_secret is None:
        raise AuthNotConfiguredError
    secret = settings.jwt_secret.get_secret_value()
    if not secret:
        raise AuthNotConfiguredError
    try:
        return TimeOptionService(
            repository=TimeOptionRepository(session),
            cursors=SignedCursorCodec(secret=secret),
        )
    except ValueError as exc:
        raise AuthNotConfiguredError from exc


def get_vote_service(session: DbSession) -> VoteService:
    return VoteService(repository=VoteRepository(session))


def get_event_service(session: DbSession) -> EventService:
    return EventService(repository=EventRepository(session))


def get_avatar_service(
    request: Request,
    session: DbSession,
    settings: SettingsDependency,
) -> AvatarService:
    temporary_source = None
    if settings.avatar_storage_backend == "cloudbase":
        if not settings.cloudbase_env_id or not settings.cloudbase_storage_public_base_url:
            logger.error(
                "CloudBase avatar storage configuration is incomplete: "
                "env_id=%s public_base_url=%s",
                bool(settings.cloudbase_env_id),
                bool(settings.cloudbase_storage_public_base_url),
            )
            raise AvatarStorageUnavailableError
        authorization = request.headers.get("x-cloudbase-authorization")
        session_token = request.headers.get("x-cloudbase-sessiontoken")
        timestamp = request.headers.get("x-cloudbase-timestamp")
        if not authorization or not session_token:
            logger.error(
                "CloudBase request credentials are incomplete: "
                "authorization=%s session_token=%s timestamp=%s",
                bool(authorization),
                bool(session_token),
                bool(timestamp),
            )
            raise AvatarStorageUnavailableError
        storage = CloudBaseAvatarStorage(
            env_id=settings.cloudbase_env_id,
            public_base_url=settings.cloudbase_storage_public_base_url,
            credentials=CloudBaseRequestCredentials(
                authorization=authorization,
                session_token=session_token,
                timestamp=timestamp,
            ),
        )
        temporary_source = storage
    else:
        storage = LocalAvatarStorage(
            root=settings.media_root,
            public_base_url=settings.media_public_base_url,
        )

    return AvatarService(
        repository=UserRepository(session),
        storage=storage,
        processor=AvatarImageProcessor(
            max_upload_bytes=settings.avatar_max_upload_bytes,
            max_dimension=settings.avatar_max_dimension,
            max_source_pixels=settings.avatar_max_source_pixels,
            jpeg_quality=settings.avatar_jpeg_quality,
        ),
        temporary_source=temporary_source,
        max_upload_bytes=settings.avatar_max_upload_bytes,
    )


def get_avatar_upload_limit(settings: SettingsDependency) -> int:
    return settings.avatar_max_upload_bytes


async def get_current_user(
    credentials: BearerCredentials,
    session: DbSession,
    settings: SettingsDependency,
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise InvalidAccessTokenError

    user_id = build_access_token_service(settings).verify(credentials.credentials)
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise InvalidAccessTokenError
    if not user.is_active:
        raise InactiveUserError
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
