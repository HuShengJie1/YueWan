from pathlib import Path

from app.integrations.storage.local import LocalAvatarStorage


async def test_local_avatar_storage_saves_and_deletes_managed_file(tmp_path: Path) -> None:
    storage = LocalAvatarStorage(
        root=tmp_path,
        public_base_url="http://testserver/media",
    )

    stored = await storage.save(b"sanitized-jpeg")

    assert stored.url.startswith("http://testserver/media/avatars/")
    saved_path = tmp_path / "avatars" / stored.url.rsplit("/", 1)[-1]
    assert saved_path.suffix == ".jpg"
    assert saved_path.read_bytes() == b"sanitized-jpeg"

    await storage.delete_url(stored.url)

    assert not saved_path.exists()


async def test_local_avatar_storage_ignores_unmanaged_urls(tmp_path: Path) -> None:
    storage = LocalAvatarStorage(
        root=tmp_path,
        public_base_url="http://testserver/media",
    )
    protected = tmp_path / "protected.jpg"
    protected.write_bytes(b"keep-me")

    await storage.delete_url("https://example.com/avatar.jpg")
    await storage.delete_url("http://testserver/media/avatars/../protected.jpg")

    assert protected.read_bytes() == b"keep-me"
