"""Validate uploads (count, size, real file type by magic bytes). Files live in memory only and are never stored."""
from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO

from ...errors import ApiError


@dataclass(frozen=True)
class Attachment:
    filename: str
    mime: str
    data: bytes


def sniff_mime(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def read_attachment(filename: str, fh: BinaryIO, max_bytes: int) -> Attachment:
    data = fh.read(max_bytes + 1)
    name = (filename or "file")[:120]
    if len(data) > max_bytes:
        raise ApiError("file_too_large", f"{name} is larger than {max_bytes // (1024 * 1024)} MB.",
                       hint="Attach a smaller photo or PDF.", status=413)
    if not data:
        raise ApiError("empty_file", f"{name} is empty.", status=422)
    mime = sniff_mime(data)
    if mime is None:
        raise ApiError("unsupported_file_type", f"{name} is not a JPEG, PNG, WebP or PDF file.",
                       hint="Attach a photo (JPEG, PNG, WebP) or a PDF.", status=415)
    return Attachment(filename=name, mime=mime, data=data)


def validate_files(files: list[tuple[str, BinaryIO]], *, max_files: int, max_bytes: int) -> list[Attachment]:
    if len(files) > max_files:
        raise ApiError("too_many_files", f"You can attach up to {max_files} files at a time.", status=422)
    return [read_attachment(name, fh, max_bytes) for name, fh in files]
