"""Storage adapters for user-managed media."""

from app.integrations.storage.base import AvatarStorage, CloudAvatarReference, StoredAvatar
from app.integrations.storage.cloudbase import CloudBaseAvatarReference
from app.integrations.storage.local import LocalAvatarStorage

__all__ = [
    "AvatarStorage",
    "CloudAvatarReference",
    "CloudBaseAvatarReference",
    "LocalAvatarStorage",
    "StoredAvatar",
]
