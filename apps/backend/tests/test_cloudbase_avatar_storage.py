import json
from collections.abc import Callable

import httpx
import pytest

from app.integrations.storage.base import (
    InvalidTemporaryAvatarError,
    TemporaryAvatarTooLargeError,
)
from app.integrations.storage.cloudbase import (
    CloudBaseAvatarStorage,
    CloudBaseRequestCredentials,
)

ENV_ID = "prod-test"
AUTHORITY = f"{ENV_ID}.bucket"
PUBLIC_BASE_URL = "https://storage.example.com"
TEMP_FILE_ID = f"cloud://{AUTHORITY}/avatar-uploads/user-1/source.upload"


def make_storage(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    timestamp: str | None = "1786723200",
) -> tuple[CloudBaseAvatarStorage, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    storage = CloudBaseAvatarStorage(
        env_id=ENV_ID,
        public_base_url=PUBLIC_BASE_URL,
        credentials=CloudBaseRequestCredentials(
            authorization="temporary-authorization",
            session_token="temporary-session-token",
            timestamp=timestamp,
        ),
        http_client=client,
    )
    return storage, client


def test_cloudbase_credentials_allow_missing_optional_timestamp() -> None:
    credentials = CloudBaseRequestCredentials(
        authorization="temporary-authorization",
        session_token="temporary-session-token",
    )

    assert credentials.as_headers() == {
        "X-CloudBase-Authorization": "temporary-authorization",
        "X-CloudBase-SessionToken": "temporary-session-token",
    }


async def test_cloudbase_storage_reads_saves_and_deletes_avatar_objects() -> None:
    uploaded_content: bytes | None = None
    deleted_file_ids: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal uploaded_content
        if request.url.host == "download.example.com":
            return httpx.Response(200, content=b"source-image")
        if request.url.host == "upload.example.com":
            uploaded_content = request.content
            return httpx.Response(204)

        assert request.headers["x-cloudbase-authorization"] == "temporary-authorization"
        assert request.headers["x-cloudbase-sessiontoken"] == "temporary-session-token"
        payload = json.loads(request.content)
        action = request.url.path.rsplit("/", 1)[-1]
        if action == "storages:batchGetTempUrls":
            assert payload == {"fileList": [{"fileID": TEMP_FILE_ID, "maxAge": 300}]}
            return httpx.Response(
                200,
                json={
                    "data": {
                        "fileList": [
                            {
                                "fileID": TEMP_FILE_ID,
                                "code": "SUCCESS",
                                "tempFileURL": "https://download.example.com/source",
                            }
                        ]
                    }
                },
            )
        if action == "storages:getUploadMetaData":
            cloud_path = payload["path"]
            return httpx.Response(
                200,
                json={
                    "data": {
                        "url": "https://upload.example.com/",
                        "authorization": "cos-authorization",
                        "token": "cos-token",
                        "fileID": f"cloud://{AUTHORITY}/{cloud_path}",
                        "cosFileID": "cos-file-id",
                    }
                },
            )
        if action == "storages:batchDelete":
            file_id = payload["fileList"][0]
            deleted_file_ids.append(file_id)
            return httpx.Response(
                200,
                json={"data": {"fileList": [{"fileID": file_id, "code": "SUCCESS"}]}},
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    storage, client = make_storage(handler)
    try:
        content = await storage.read_temporary(
            TEMP_FILE_ID,
            owner_key="user-1",
            max_bytes=1024,
        )
        stored = await storage.save(b"processed-jpeg")
        await storage.delete_url(stored.url)
        await storage.delete_file_id(TEMP_FILE_ID)
    finally:
        await client.aclose()

    assert content == b"source-image"
    assert stored.url.startswith(f"{PUBLIC_BASE_URL}/avatars/")
    assert uploaded_content is not None
    assert b"processed-jpeg" in uploaded_content
    assert b"image/jpeg" in uploaded_content
    assert deleted_file_ids == [
        stored.url.replace(PUBLIC_BASE_URL, f"cloud://{AUTHORITY}"),
        TEMP_FILE_ID,
    ]


async def test_cloudbase_storage_rejects_foreign_or_wrong_owner_file_ids() -> None:
    storage, client = make_storage(lambda _request: pytest.fail("HTTP must not be called"))
    try:
        with pytest.raises(InvalidTemporaryAvatarError):
            await storage.read_temporary(
                "cloud://other-env.bucket/avatar-uploads/user-1/source",
                owner_key="user-1",
                max_bytes=1024,
            )
        with pytest.raises(InvalidTemporaryAvatarError):
            await storage.read_temporary(
                f"cloud://{AUTHORITY}/avatar-uploads/user-2/source",
                owner_key="user-1",
                max_bytes=1024,
            )
    finally:
        await client.aclose()


async def test_cloudbase_storage_enforces_download_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "download.example.com":
            return httpx.Response(200, content=b"too-large")
        return httpx.Response(
            200,
            json={
                "data": {
                    "fileList": [
                        {
                            "fileID": TEMP_FILE_ID,
                            "code": "SUCCESS",
                            "tempFileURL": "https://download.example.com/source",
                        }
                    ]
                }
            },
        )

    storage, client = make_storage(handler)
    try:
        with pytest.raises(TemporaryAvatarTooLargeError):
            await storage.read_temporary(TEMP_FILE_ID, owner_key="user-1", max_bytes=3)
    finally:
        await client.aclose()
