"""media-worker (PRD C6): re-encoding strips metadata, sizes, guards, path safety, idempotent results."""

from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from PIL import Image

from cimh_common.outbox import EventEnvelope, new_event
from media_worker import imaging
from media_worker.imaging import ImageRejected, process
from media_worker.worker import MediaWorker, Settings, file_id_for

SCHEMAS = Path(__file__).resolve().parents[3] / "packages" / "event-schemas" / "schemas"


def schema(etype: str) -> Draft202012Validator:
    index = json.loads((SCHEMAS / "index.json").read_text(encoding="utf-8"))
    return Draft202012Validator(json.loads((SCHEMAS / index[etype]).read_text(encoding="utf-8")))


def photo(
    path: Path, size: tuple[int, int] = (2400, 1200), *, orientation: int | None = None, fmt: str = "JPEG"
) -> Path:
    im = Image.new("RGB", size, (200, 30, 30))
    im.paste((10, 10, 220), (0, 0, size[0] // 2, size[1]))  # left half blue: shows rotation
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"  # Make
    exif[0x0110] = "Model X"  # Model
    exif[0x8825] = {2: (13.0, 5.0, 0.0)}  # GPS IFD (latitude)
    if orientation:
        exif[0x0112] = orientation
    im.save(path, fmt, exif=exif.tobytes(), quality=90)
    return path


class FakeProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any], bytes | None]] = []

    async def send_and_wait(self, topic: str, value: bytes, key: bytes | None = None) -> None:
        EventEnvelope.model_validate_json(value)  # what every consumer does first (extra fields are refused)
        self.sent.append((topic, json.loads(value), key))


def job(source: str, product: str = "MET0001", job_id: str = "JOBABC123", bg: bool = False) -> Any:
    payload = {"jobId": job_id, "productId": product, "sourcePath": source, "removeBackground": bg}
    evt = new_event("image.process", payload, correlation_id="corr-1", actor_id="USRSTAFF")
    schema("image.process").validate(json.loads(evt.model_dump_json()))
    return evt


def test_reencoding_strips_metadata_and_keeps_photos_upright(tmp_path: Path) -> None:
    src = photo(tmp_path / "in.jpg", (1000, 500), orientation=6)  # 6 = rotate 90° clockwise to view
    out = process(src, tmp_path / "out", "IMG1", remove_background=False, remover=None)
    assert (out.width, out.height) == (500, 1000)  # rotated by the EXIF orientation
    assert [f.name for f in out.files] == ["IMG1.webp", "IMG1@800.webp", "IMG1@320.webp"]
    for f in out.files:
        with Image.open(f) as im:
            assert im.format == "WEBP"
            assert not im.getexif()  # no camera make/model, no GPS
            assert "icc_profile" not in im.info
            assert "xmp" not in im.info
            assert max(im.size) <= 1600
    with Image.open(out.files[2]) as small:
        assert max(small.size) == 320
    assert b"SecretCam" not in out.files[0].read_bytes()


def test_sizes_never_upscale_and_alpha_is_kept(tmp_path: Path) -> None:
    src = tmp_path / "small.png"
    Image.new("RGBA", (200, 100), (0, 0, 0, 0)).save(src)
    out = process(src, tmp_path / "out", "IMG2", remove_background=False, remover=None)
    assert (out.width, out.height) == (200, 100)
    with Image.open(out.files[0]) as im:
        assert im.mode == "RGBA"
    big_src = photo(tmp_path / "big.jpg", (4000, 3000))
    big = process(big_src, tmp_path / "o2", "IMG3", remove_background=False, remover=None)
    assert (big.width, big.height) == (1600, 1200)


def test_background_remover_is_used_when_asked(tmp_path: Path) -> None:
    seen: list[str] = []

    def remover(im: Image.Image) -> Image.Image:
        seen.append(im.mode)
        im.paste((0, 0, 0, 0), (0, 0, 50, 50))  # cut out a corner, as rembg would
        return im

    src = photo(tmp_path / "a.jpg", (300, 300))
    out = process(src, tmp_path / "o", "IMG4", remove_background=True, remover=remover)
    assert seen == ["RGBA"]
    with Image.open(out.files[0]) as im:
        assert im.mode == "RGBA"
    process(src, tmp_path / "o", "IMG5", remove_background=False, remover=remover)
    assert seen == ["RGBA"]


def test_bad_inputs_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    junk = tmp_path / "junk.jpg"
    junk.write_bytes(b"\xff\xd8\xff\xe0 not really a jpeg")
    with pytest.raises(ImageRejected):
        process(junk, tmp_path / "o", "X", remove_background=False, remover=None)
    gif = tmp_path / "a.gif"
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    with pytest.raises(ImageRejected, match="unsupported"):
        process(gif, tmp_path / "o", "X", remove_background=False, remover=None)
    monkeypatch.setattr(imaging, "MAX_PIXELS", 1000)  # decompression-bomb guard
    with pytest.raises(ImageRejected):
        process(photo(tmp_path / "b.jpg", (100, 100)), tmp_path / "o", "X", remove_background=False, remover=None)


def worker(tmp_path: Path, remover: Any = None) -> tuple[MediaWorker, FakeProducer]:
    producer = FakeProducer()
    return MediaWorker(Settings(media_root=tmp_path), producer, remover), producer


def test_job_writes_public_files_reports_and_removes_the_original(tmp_path: Path) -> None:
    (tmp_path / "incoming").mkdir()
    photo(tmp_path / "incoming" / "a1b2c3d4e5f6.jpg")
    w, producer = worker(tmp_path)
    asyncio.run(w.handle(job("incoming/a1b2c3d4e5f6.jpg")))

    assert not (tmp_path / "incoming" / "a1b2c3d4e5f6.jpg").exists()
    files = sorted(p.name for p in (tmp_path / "public" / "products" / "MET0001").iterdir())
    assert files == ["IMGABC123.webp", "IMGABC123@320.webp", "IMGABC123@800.webp"]
    topic, result, key = producer.sent[0]
    assert (topic, key) == ("media.results", b"MET0001")
    schema("image.processed").validate(result)
    assert result["correlationId"] == "corr-1"
    assert result["payload"] == {
        "jobId": "JOBABC123", "productId": "MET0001", "ok": True, "fileId": "IMGABC123",
        "url": "/media/products/MET0001/IMGABC123.webp", "w": 1600, "h": 800,
    }  # fmt: skip

    # Redelivered after success: same answer, nothing new written.
    asyncio.run(w.handle(job("incoming/a1b2c3d4e5f6.jpg")))
    assert producer.sent[1][1]["payload"] == result["payload"]


@pytest.mark.parametrize(
    "source", ["../etc/passwd", "incoming/../../x.jpg", "public/products/x.webp", "incoming/a.gif", "/abs/x.jpg"]
)
def test_sources_outside_incoming_are_never_read(tmp_path: Path, source: str) -> None:
    w, producer = worker(tmp_path)
    asyncio.run(w.handle(job(source)))
    assert producer.sent[0][1]["payload"]["ok"] is False
    assert producer.sent[0][1]["payload"]["error"] == "invalid source path"


def test_unusable_or_missing_files_are_reported(tmp_path: Path) -> None:
    (tmp_path / "incoming").mkdir()
    (tmp_path / "incoming" / "badbadbad1.jpg").write_bytes(b"\xff\xd8\xff garbage")
    w, producer = worker(tmp_path)
    asyncio.run(w.handle(job("incoming/badbadbad1.jpg")))
    assert producer.sent[0][1]["payload"]["ok"] is False
    assert "not a usable image" in producer.sent[0][1]["payload"]["error"]
    assert not (tmp_path / "incoming" / "badbadbad1.jpg").exists()
    asyncio.run(w.handle(job("incoming/missing123.jpg", job_id="JOBZZZ")))
    assert producer.sent[1][1]["payload"]["error"] == "source file missing"
    schema("image.processed").validate(producer.sent[1][1])


def test_malformed_jobs_go_to_the_dlq_and_others_are_ignored(tmp_path: Path) -> None:
    w, producer = worker(tmp_path)
    with pytest.raises(ValueError, match="bad jobId"):
        asyncio.run(w.handle(job("incoming/abcdefgh.jpg", product="../../etc")))
    asyncio.run(w.handle(new_event("something.else", {}, correlation_id="c")))
    assert producer.sent == []
    assert file_id_for("JOB123") == "IMG123"


def test_photo_bytes_round_trip() -> None:
    buf = BytesIO()
    Image.new("RGB", (4, 4)).save(buf, "WEBP")
    assert buf.getvalue()[8:12] == b"WEBP"
