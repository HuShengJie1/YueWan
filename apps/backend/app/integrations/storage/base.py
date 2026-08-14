from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredAvatar:
    url: str


class InvalidTemporaryAvatarError(ValueError):
    """The supplied cloud file does not belong to the expected temporary path."""


class TemporaryAvatarTooLargeError(ValueError):
    """The temporary cloud object exceeds the avatar upload limit."""


class AvatarStorage(Protocol):
    async def save(self, content: bytes) -> StoredAvatar: ...

    async def delete_url(self, url: str) -> None: ...


class TemporaryAvatarSource(Protocol):
    async def read_temporary(
        self,
        file_id: str,
        *,
        owner_key: str,
        max_bytes: int,
    ) -> bytes: ...

    async def delete_file_id(self, file_id: str) -> None: ...
