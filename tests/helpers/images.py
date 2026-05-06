"""Tiny inline image byte blobs for upload tests.

Per `.specs/ai_gen/implementation_plan.md` §Phase 4 the backend detects
MIME by reading the first 32 bytes: JPEG starts with ``FF D8 FF``, PNG
with ``89 50 4E 47 0D 0A 1A 0A``. These constants are the smallest blobs
that satisfy that sniff while still resembling real files (JPEG has the
``FF D9`` end-of-image marker; PNG carries its 8-byte signature).

Per `.specs/ai_gen/testing_strategy.md` §6 (Image bytes are inline),
fixtures must not reference files on disk.
"""

from __future__ import annotations

# 4-byte JFIF SOI/APP0 prefix + zero padding + 2-byte EOI.
JPEG_BYTES: bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 60 + b"\xff\xd9"

# 8-byte PNG signature + zero padding (no IHDR/IDAT — backend only sniffs
# the signature; we never decode these bytes).
PNG_BYTES: bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 60
