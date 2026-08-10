import os
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

MANAGED_AVATAR_KEY = re.compile(r"avatars/[0-9a-f]{32}\.jpg")


@dataclass(frozen=True, slots=True)
class StoredAvatar:
    url: str


class LocalAvatarStorage:
    """Atomically persist sanitized avatars under a configured local media root."""

    def __init__(self, *, root: Path, public_base_url: str) -> None:
        self._root = root.resolve()
        self._public_base_url = public_base_url.rstrip("/")

    async def save(self, content: bytes) -> StoredAvatar:
        return await run_in_threadpool(self._save, content)

    def _save(self, content: bytes) -> StoredAvatar:
        avatars_directory = self._root / "avatars"
        avatars_directory.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4().hex}.jpg"
        final_path = avatars_directory / filename
        temporary_path = avatars_directory / f".{filename}.{uuid4().hex}.tmp"

        try:
            with temporary_path.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, final_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

        return StoredAvatar(url=f"{self._public_base_url}/avatars/{filename}")

    async def delete_url(self, url: str) -> None:
        path = self._managed_path(url)
        if path is not None:
            await run_in_threadpool(path.unlink, True)

    def _managed_path(self, url: str) -> Path | None:
        prefix = f"{self._public_base_url}/"
        if not url.startswith(prefix):
            return None
        key = url.removeprefix(prefix)
        if MANAGED_AVATAR_KEY.fullmatch(key) is None:
            return None

        path = (self._root / key).resolve()
        if self._root not in path.parents:
            return None
        return path
