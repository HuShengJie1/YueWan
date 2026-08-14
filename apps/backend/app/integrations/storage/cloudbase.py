import re
from urllib.parse import urlsplit

from app.integrations.storage.base import (
    InvalidCloudAvatarReferenceError,
    StoredAvatar,
)

MANAGED_AVATAR_FILENAME = re.compile(r"[0-9]{13}-[0-9a-f]{16}\.(?:jpg|png)")


class CloudBaseAvatarReference:
    """Validate a client-created avatar file ID and expose its stable public URL."""

    def __init__(self, *, env_id: str, public_base_url: str) -> None:
        self._env_id = env_id
        self._public_base_url = public_base_url.rstrip("/")

    def resolve(self, file_id: str, *, owner_key: str) -> StoredAvatar:
        authority, cloud_path = self._parse_file_id(file_id)
        if not self._is_current_environment(authority):
            raise InvalidCloudAvatarReferenceError

        expected_prefix = f"avatars/{owner_key}/"
        if not cloud_path.startswith(expected_prefix):
            raise InvalidCloudAvatarReferenceError
        filename = cloud_path.removeprefix(expected_prefix)
        if MANAGED_AVATAR_FILENAME.fullmatch(filename) is None:
            raise InvalidCloudAvatarReferenceError

        return StoredAvatar(url=f"{self._public_base_url}/{cloud_path}")

    @staticmethod
    def _parse_file_id(file_id: str) -> tuple[str, str]:
        parsed = urlsplit(file_id)
        path = parsed.path.lstrip("/")
        if (
            parsed.scheme != "cloud"
            or not parsed.netloc
            or not path
            or parsed.query
            or parsed.fragment
            or ".." in path.split("/")
        ):
            raise InvalidCloudAvatarReferenceError
        return parsed.netloc, path

    def _is_current_environment(self, authority: str) -> bool:
        return authority == self._env_id or authority.startswith(f"{self._env_id}.")
