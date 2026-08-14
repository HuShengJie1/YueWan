import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.integrations.storage.base import (
    InvalidTemporaryAvatarError,
    StoredAvatar,
    TemporaryAvatarTooLargeError,
)

CLOUDBASE_OPEN_API_BASE_URL = "https://tcb-api.tencentcloudapi.com/api/v2"
MANAGED_AVATAR_KEY = re.compile(r"avatars/[0-9a-f]{32}\.jpg")
TEMPORARY_FILENAME = re.compile(r"[0-9A-Za-z._-]{1,128}")


@dataclass(frozen=True, slots=True)
class CloudBaseRequestCredentials:
    authorization: str
    session_token: str
    timestamp: str

    def as_headers(self) -> dict[str, str]:
        return {
            "X-CloudBase-Authorization": self.authorization,
            "X-CloudBase-SessionToken": self.session_token,
            "X-CloudBase-TimeStamp": self.timestamp,
        }


class CloudBaseAvatarStorage:
    """Read temporary uploads and persist sanitized avatars in CloudBase storage."""

    def __init__(
        self,
        *,
        env_id: str,
        public_base_url: str,
        credentials: CloudBaseRequestCredentials,
        timeout_seconds: float = 10.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._env_id = env_id
        self._public_base_url = public_base_url.rstrip("/")
        self._credentials = credentials
        self._timeout = httpx.Timeout(timeout_seconds)
        self._http_client = http_client
        self._file_id_authority: str | None = None

    async def read_temporary(
        self,
        file_id: str,
        *,
        owner_key: str,
        max_bytes: int,
    ) -> bytes:
        self._validate_temporary_file_id(file_id, owner_key=owner_key)
        self._remember_authority(file_id)

        async with self._client() as client:
            payload = await self._post_open_api(
                client,
                action="storages:batchGetTempUrls",
                json={"fileList": [{"fileID": file_id, "maxAge": 300}]},
            )
            file_list = payload.get("fileList")
            if not isinstance(file_list, list) or len(file_list) != 1:
                raise OSError("CloudBase returned invalid download metadata")
            item = file_list[0]
            if not isinstance(item, dict) or item.get("code") != "SUCCESS":
                raise InvalidTemporaryAvatarError
            temporary_url = item.get("tempFileURL")
            if not isinstance(temporary_url, str) or not self._is_https_url(temporary_url):
                raise OSError("CloudBase returned an invalid download URL")

            try:
                async with client.stream("GET", temporary_url) as response:
                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    if content_length is not None:
                        try:
                            parsed_content_length = int(content_length)
                        except ValueError as exc:
                            raise OSError(
                                "Cloud storage returned an invalid content length"
                            ) from exc
                        if parsed_content_length > max_bytes:
                            raise TemporaryAvatarTooLargeError

                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > max_bytes:
                            raise TemporaryAvatarTooLargeError
                    return bytes(content)
            except TemporaryAvatarTooLargeError:
                raise
            except httpx.HTTPError as exc:
                raise OSError("Unable to download temporary avatar") from exc

    async def save(self, content: bytes) -> StoredAvatar:
        cloud_path = f"avatars/{uuid4().hex}.jpg"
        async with self._client() as client:
            metadata = await self._post_open_api(
                client,
                action="storages:getUploadMetaData",
                json={"path": cloud_path},
            )
            upload_url = metadata.get("url")
            authorization = metadata.get("authorization")
            token = metadata.get("token")
            file_id = metadata.get("fileID")
            cos_file_id = metadata.get("cosFileID")
            if not all(
                isinstance(value, str) and value
                for value in (upload_url, authorization, token, file_id, cos_file_id)
            ):
                raise OSError("CloudBase returned invalid upload metadata")
            if not self._is_https_url(upload_url):
                raise OSError("CloudBase returned an invalid upload URL")
            self._validate_managed_file_id(file_id, expected_path=cloud_path)
            self._remember_authority(file_id)

            try:
                response = await client.post(
                    upload_url,
                    data={
                        "Signature": authorization,
                        "x-cos-security-token": token,
                        "x-cos-meta-fileid": cos_file_id,
                        "key": cloud_path,
                    },
                    files={"file": ("avatar.jpg", content, "image/jpeg")},
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise OSError("Unable to upload processed avatar") from exc

        return StoredAvatar(url=f"{self._public_base_url}/{cloud_path}")

    async def delete_url(self, url: str) -> None:
        prefix = f"{self._public_base_url}/"
        if not url.startswith(prefix):
            return
        cloud_path = url.removeprefix(prefix)
        if MANAGED_AVATAR_KEY.fullmatch(cloud_path) is None:
            return
        if self._file_id_authority is None:
            return
        await self.delete_file_id(f"cloud://{self._file_id_authority}/{cloud_path}")

    async def delete_file_id(self, file_id: str) -> None:
        authority, cloud_path = self._parse_file_id(file_id)
        if not self._is_current_environment(authority):
            return
        if not (
            cloud_path.startswith("avatar-uploads/")
            or MANAGED_AVATAR_KEY.fullmatch(cloud_path) is not None
        ):
            return

        async with self._client() as client:
            payload = await self._post_open_api(
                client,
                action="storages:batchDelete",
                json={"fileList": [file_id]},
            )
        file_list = payload.get("fileList")
        if not isinstance(file_list, list) or len(file_list) != 1:
            raise OSError("CloudBase returned invalid deletion metadata")
        item = file_list[0]
        if not isinstance(item, dict) or item.get("code") != "SUCCESS":
            raise OSError("CloudBase failed to delete an avatar object")

    def _validate_temporary_file_id(self, file_id: str, *, owner_key: str) -> None:
        authority, cloud_path = self._parse_file_id(file_id)
        if not self._is_current_environment(authority):
            raise InvalidTemporaryAvatarError
        expected_prefix = f"avatar-uploads/{owner_key}/"
        if not cloud_path.startswith(expected_prefix):
            raise InvalidTemporaryAvatarError
        filename = cloud_path.removeprefix(expected_prefix)
        if TEMPORARY_FILENAME.fullmatch(filename) is None:
            raise InvalidTemporaryAvatarError

    def _validate_managed_file_id(self, file_id: str, *, expected_path: str) -> None:
        try:
            authority, cloud_path = self._parse_file_id(file_id)
        except InvalidTemporaryAvatarError as exc:
            raise OSError("CloudBase returned an unexpected managed file ID") from exc
        if not self._is_current_environment(authority) or cloud_path != expected_path:
            raise OSError("CloudBase returned an unexpected managed file ID")

    @staticmethod
    def _parse_file_id(file_id: str) -> tuple[str, str]:
        parsed = urlsplit(file_id)
        path = parsed.path.lstrip("/")
        if parsed.scheme != "cloud" or not parsed.netloc or not path or ".." in path.split("/"):
            raise InvalidTemporaryAvatarError
        return parsed.netloc, path

    def _is_current_environment(self, authority: str) -> bool:
        return authority == self._env_id or authority.startswith(f"{self._env_id}.")

    def _remember_authority(self, file_id: str) -> None:
        authority, _ = self._parse_file_id(file_id)
        if self._is_current_environment(authority):
            self._file_id_authority = authority

    @staticmethod
    def _is_https_url(value: str) -> bool:
        parsed = urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.netloc)

    async def _post_open_api(
        self,
        client: httpx.AsyncClient,
        *,
        action: str,
        json: dict[str, object],
    ) -> dict[str, object]:
        url = f"{CLOUDBASE_OPEN_API_BASE_URL}/envs/{self._env_id}/{action}"
        try:
            response = await client.post(
                url,
                headers=self._credentials.as_headers(),
                json=json,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise OSError("CloudBase storage API is unavailable") from exc
        if not isinstance(payload, dict):
            raise OSError("CloudBase returned an invalid response")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise OSError("CloudBase storage operation failed")
        return data

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._http_client is not None:
            yield self._http_client
            return
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            yield client
