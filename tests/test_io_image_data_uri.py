import base64
from pathlib import Path

from astrbot.core.utils.io import detect_image_mime_type, image_source_to_data_uri

PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
GIF_BYTES = b"GIF89a\x01\x00\x01\x00\x80\x00\x00"
WEBP_BYTES = b"RIFF\x0c\x00\x00\x00WEBPVP8 "
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF"


def test_detect_image_mime_type_known_formats():
    assert detect_image_mime_type(PNG_BYTES) == "image/png"
    assert detect_image_mime_type(JPEG_BYTES) == "image/jpeg"
    assert detect_image_mime_type(GIF_BYTES) == "image/gif"
    assert detect_image_mime_type(WEBP_BYTES) == "image/webp"


def test_detect_image_mime_type_unknown_fallback_jpeg():
    assert detect_image_mime_type(b"not-an-image") == "image/jpeg"


def test_image_source_to_data_uri_passthrough_data_uri():
    data_uri = f"data:image/png;base64,{base64.b64encode(PNG_BYTES).decode('utf-8')}"
    encoded, mime_type = image_source_to_data_uri(data_uri)
    assert encoded == data_uri
    assert mime_type == "image/png"


def test_image_source_to_data_uri_detects_base64_mime():
    raw = base64.b64encode(GIF_BYTES).decode("utf-8")
    encoded, mime_type = image_source_to_data_uri(f"base64://{raw}")
    assert encoded.startswith("data:image/gif;base64,")
    assert mime_type == "image/gif"


def test_image_source_to_data_uri_invalid_base64_fallback_jpeg():
    encoded, mime_type = image_source_to_data_uri("base64://not-valid-base64")
    assert encoded == "data:image/jpeg;base64,not-valid-base64"
    assert mime_type == "image/jpeg"


def test_image_source_to_data_uri_detects_local_file_mime(tmp_path: Path):
    webp_path = tmp_path / "image.webp"
    webp_path.write_bytes(WEBP_BYTES)

    encoded, mime_type = image_source_to_data_uri(str(webp_path))
    assert encoded.startswith("data:image/webp;base64,")
    assert mime_type == "image/webp"
