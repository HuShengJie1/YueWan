from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredAvatar:
    url: str


class InvalidCloudAvatarReferenceError(ValueError):
    """The supplied cloud file is not a managed avatar for the current user."""


class AvatarStorage(Protocol):
    async def save(self, content: bytes) -> StoredAvatar: ...

    async def delete_url(self, url: str) -> None: ...


class CloudAvatarReference(Protocol):
    def resolve(self, file_id: str, *, owner_key: str) -> StoredAvatar: ...
