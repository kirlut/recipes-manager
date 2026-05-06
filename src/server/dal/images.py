"""Image bytes → shared volume. UUID4-named filenames."""

from __future__ import annotations

import uuid
from pathlib import Path


def write_image(image_dir: str, payload: bytes, ext: str) -> str:
    """Write `payload` to `<image_dir>/<uuid4><ext>` and return the filename.

    The directory is created if missing (also done at startup, but the
    safety net is cheap and keeps tests deterministic if someone clears
    the volume between runs).
    """
    directory = Path(image_dir)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}{ext}"
    (directory / filename).write_bytes(payload)
    return filename
