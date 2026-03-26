import base64

PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
GIF_BYTES = b"GIF89a\x01\x00\x01\x00\x80\x00\x00"
WEBP_BYTES = b"RIFF\x0c\x00\x00\x00WEBPVP8 "
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF"

PNG_BASE64 = base64.b64encode(PNG_BYTES).decode("ascii")
GIF_BASE64 = base64.b64encode(GIF_BYTES).decode("ascii")
WEBP_BASE64 = base64.b64encode(WEBP_BYTES).decode("ascii")
JPEG_BASE64 = base64.b64encode(JPEG_BYTES).decode("ascii")
