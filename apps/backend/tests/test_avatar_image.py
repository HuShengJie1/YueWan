from io import BytesIO

import pytest
from PIL import Image

from app.core.exceptions import (
    AvatarFileTooLargeError,
    InvalidAvatarImageError,
    UnsupportedAvatarTypeError,
)
from app.services.avatar import AvatarImageProcessor


def build_processor(**overrides: int) -> AvatarImageProcessor:
    options = {
        "max_upload_bytes": 5 * 1024 * 1024,
        "max_dimension": 512,
        "max_source_pixels": 20_000_000,
        "jpeg_quality": 85,
    }
    options.update(overrides)
    return AvatarImageProcessor(**options)


def make_image(*, image_format: str, size: tuple[int, int] = (1000, 800)) -> bytes:
    image = Image.new("RGBA", size, (30, 80, 140, 128))
    output = BytesIO()
    if image_format == "JPEG":
        image.convert("RGB").save(output, format=image_format)
    else:
        image.save(output, format=image_format)
    image.close()
    return output.getvalue()


@pytest.mark.parametrize("image_format", ["JPEG", "PNG", "WEBP"])
def test_avatar_processor_normalizes_supported_images(image_format: str) -> None:
    processed = build_processor().process(make_image(image_format=image_format))

    assert processed.width == 512
    assert processed.height == 410
    with Image.open(BytesIO(processed.content)) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.size == (512, 410)
        assert image.getexif() == {}


def test_avatar_processor_rejects_empty_or_invalid_images() -> None:
    processor = build_processor()

    with pytest.raises(InvalidAvatarImageError):
        processor.process(b"")
    with pytest.raises(InvalidAvatarImageError):
        processor.process(b"not-an-image")


def test_avatar_processor_rejects_unsupported_image_format() -> None:
    with pytest.raises(UnsupportedAvatarTypeError):
        build_processor().process(make_image(image_format="GIF"))


def test_avatar_processor_enforces_file_and_pixel_limits() -> None:
    content = make_image(image_format="PNG", size=(100, 100))

    with pytest.raises(AvatarFileTooLargeError):
        build_processor(max_upload_bytes=len(content) - 1).process(content)
    with pytest.raises(AvatarFileTooLargeError):
        build_processor(max_source_pixels=9_999).process(content)
