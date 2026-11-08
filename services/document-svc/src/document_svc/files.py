"""Bytes on the volume, type sniffing, image re-encoding and the virus scanner.

Layout (BSD §2):
    protected/orders/<orderId>/<fileId>.<ext>   uploads and generated PDFs
    protected/labels/<fileId>.pdf               unit-label batches
    protected/meta/<fileId>.json                metadata sidecar (document-svc owns no collection)
    quarantine/<fileId>.bin (+ .json)           infected uploads; never served, kept for staff to inspect
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import struct
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

EXT = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_ID = re.compile(r"^FIL[0-9A-Za-z]{10,40}$")
_REQ = re.compile(r"^[0-9A-Za-z_-]{1,64}$")


def sniff(data: bytes) -> str | None:
    """MIME type from the content (magic bytes), never from the name or the client's Content-Type."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def reencode(data: bytes, mime: str) -> bytes:
    """Decode and re-encode an image: drops EXIF/GPS and anything appended to it. Raises on a bad image."""
    with Image.open(io.BytesIO(data)) as src:
        src.load()
        out = io.BytesIO()
        fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[mime]
        im: Image.Image = src.convert("RGB") if fmt == "JPEG" and src.mode not in ("RGB", "L") else src
        if fmt == "PNG":
            im.save(out, format=fmt)
        else:
            im.save(out, format=fmt, quality=90)
        return out.getvalue()


def safe_name(name: str | None, ext: str) -> str:
    base = Path((name or "").replace("\\", "/")).name
    base = re.sub(r"[^\w .()-]", "_", base).strip(" .")[:120] or "file"
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return f"{stem}.{ext}"


def valid_file_id(fid: str) -> bool:
    return bool(_ID.match(fid))


class FileStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def rel_path(self, meta: dict[str, Any]) -> str:
        ext = EXT.get(meta["mime"], "bin")
        if meta.get("requestId"):
            if not _REQ.match(meta["requestId"]):
                raise ValueError("bad request id")
            return f"protected/orders/{meta['requestId']}/{meta['id']}.{ext}"
        return f"protected/labels/{meta['id']}.{ext}"

    def _meta_path(self, fid: str) -> Path:
        return self.root / "protected" / "meta" / f"{fid}.json"

    @staticmethod
    def _atomic(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

    def save(self, meta: dict[str, Any], data: bytes) -> None:
        """Bytes first, then the sidecar: a file is visible only once both are complete."""
        self._atomic(self.root / self.rel_path(meta), data)
        self.write_meta(meta)

    def write_meta(self, meta: dict[str, Any]) -> None:
        self._atomic(self._meta_path(meta["id"]), json.dumps(meta, default=str).encode())

    def meta(self, fid: str) -> dict[str, Any] | None:
        if not valid_file_id(fid):
            return None
        try:
            out: dict[str, Any] = json.loads(self._meta_path(fid).read_bytes())
        except (FileNotFoundError, ValueError):
            return None
        return out

    def remove(self, meta: dict[str, Any]) -> None:
        for p in (self.root / self.rel_path(meta), self._meta_path(meta["id"])):
            p.unlink(missing_ok=True)

    def quarantine(self, fid: str, data: bytes, info: dict[str, Any]) -> None:
        q = self.root / "quarantine"
        self._atomic(q / f"{fid}.bin", data)
        self._atomic(q / f"{fid}.json", json.dumps(info, default=str).encode())


# ---------------------------------------------------------------- virus scanning (TR-SEC-6)


class ScannerDown(Exception):
    pass


class Scanner(Protocol):
    async def scan(self, data: bytes) -> str | None:
        """Signature name if infected, None if clean. Raises ScannerDown if it can't tell."""
        ...

    async def ready(self) -> bool: ...


class NoScanner:
    """SCAN_ENABLED=false (staging-lite only)."""

    async def scan(self, data: bytes) -> str | None:
        return None

    async def ready(self) -> bool:
        return True


class ClamdScanner:
    """clamd INSTREAM over TCP: <len:uint32 BE><chunk>... <0:uint32> -> "stream: OK" | "stream: <sig> FOUND"."""

    def __init__(self, host: str, port: int, timeout: float = 30.0, chunk: int = 64 * 1024) -> None:
        self.host, self.port, self.timeout, self.chunk = host, port, timeout, chunk

    async def _talk(self, payload: list[bytes]) -> bytes:
        try:
            async with asyncio.timeout(self.timeout):
                reader, writer = await asyncio.open_connection(self.host, self.port)
                try:
                    for part in payload:
                        writer.write(part)
                    await writer.drain()
                    return await reader.read()
                finally:
                    writer.close()
        except (OSError, TimeoutError) as exc:
            raise ScannerDown(str(exc)) from exc

    async def scan(self, data: bytes) -> str | None:
        parts = [b"zINSTREAM\0"]
        for i in range(0, len(data), self.chunk):
            piece = data[i : i + self.chunk]
            parts += [struct.pack(">I", len(piece)), piece]
        parts.append(struct.pack(">I", 0))
        reply = (await self._talk(parts)).rstrip(b"\0").decode(errors="replace").strip()
        if reply.endswith("OK"):
            return None
        if reply.endswith("FOUND"):
            return reply.split(":", 1)[-1].removesuffix("FOUND").strip() or "unknown"
        raise ScannerDown(f"clamd: {reply[:200]}")  # e.g. size limit exceeded: never store unscanned

    async def ready(self) -> bool:
        try:
            return (await self._talk([b"zPING\0"])).rstrip(b"\0").strip() == b"PONG"
        except ScannerDown:
            return False
