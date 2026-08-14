"""Storage adapters for user-managed media."""

from app.integrations.storage.base import AvatarStorage, StoredAvatar, TemporaryAvatarSource
from app.integrations.storage.cloudbase import (
    CloudBaseAvatarStorage,
    CloudBaseRequestCredentials,
)
from app.integrations.storage.local import LocalAvatarStorage

__all__ = [
    "AvatarStorage",
    "CloudBaseAvatarStorage",
    "CloudBaseRequestCredentials",
    "LocalAvatarStorage",
    "StoredAvatar",
    "TemporaryAvatarSource",
]
