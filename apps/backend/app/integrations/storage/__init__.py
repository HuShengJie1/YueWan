"""Storage adapters for user-managed media."""

from app.integrations.storage.local import LocalAvatarStorage, StoredAvatar

__all__ = ["LocalAvatarStorage", "StoredAvatar"]
