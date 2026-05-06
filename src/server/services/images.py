"""Image MIME sniffing.

JPEG starts with `FF D8 FF`; PNG with `89 50 4E 47 0D 0A 1A 0A`. We never
trust the multipart `Content-Type` — only the leading bytes of the payload.
"""

from __future__ import annotations

from api.errors import UnsupportedMediaTypeError

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def detect_extension(sniff: bytes) -> str:
    """Return `".jpg"` or `".png"` based on magic bytes; otherwise raise 415."""
    if sniff.startswith(_JPEG_MAGIC):
        return ".jpg"
    if sniff.startswith(_PNG_MAGIC):
        return ".png"
    raise UnsupportedMediaTypeError(
        "Uploaded file is not a JPEG or PNG image (header sniff failed)."
    )
