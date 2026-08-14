import pytest

from app.integrations.storage.base import InvalidCloudAvatarReferenceError
from app.integrations.storage.cloudbase import CloudBaseAvatarReference

ENV_ID = "prod-test"
AUTHORITY = f"{ENV_ID}.bucket"
PUBLIC_BASE_URL = "https://storage.example.com"
OWNER_KEY = "user-1"
FILENAME = "1786723200000-0123456789abcdef.jpg"


def make_reference() -> CloudBaseAvatarReference:
    return CloudBaseAvatarReference(env_id=ENV_ID, public_base_url=PUBLIC_BASE_URL)


def test_cloudbase_reference_resolves_current_user_avatar() -> None:
    stored = make_reference().resolve(
        f"cloud://{AUTHORITY}/avatars/{OWNER_KEY}/{FILENAME}",
        owner_key=OWNER_KEY,
    )

    assert stored.url == f"{PUBLIC_BASE_URL}/avatars/{OWNER_KEY}/{FILENAME}"


@pytest.mark.parametrize(
    "file_id",
    [
        f"cloud://other-env.bucket/avatars/{OWNER_KEY}/{FILENAME}",
        f"cloud://{AUTHORITY}/avatars/user-2/{FILENAME}",
        f"cloud://{AUTHORITY}/avatars/{OWNER_KEY}/avatar.jpg",
        f"cloud://{AUTHORITY}/avatars/{OWNER_KEY}/1786723200000-0123456789abcdef.svg",
        f"cloud://{AUTHORITY}/avatars/{OWNER_KEY}/../{FILENAME}",
        f"cloud://{AUTHORITY}/avatars/{OWNER_KEY}/{FILENAME}?download=1",
    ],
)
def test_cloudbase_reference_rejects_unmanaged_file_ids(file_id: str) -> None:
    with pytest.raises(InvalidCloudAvatarReferenceError):
        make_reference().resolve(file_id, owner_key=OWNER_KEY)
