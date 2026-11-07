"""Image processing for product photos (PRD C6, TRD TR-SEC: uploads are re-encoded, metadata stripped).

Every upload is decoded and written again as WebP, so nothing but pixels survives: no EXIF (GPS, camera
serials), no ICC/XMP, no trailing payloads. Orientation from EXIF is applied first so photos stay upright.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

# Decompression-bomb guard: 40 MP is a 7300 x 5500 photo, far above any product shot.
MAX_PIXELS = 40_000_000
SIZES = {"": 1600, "@800": 800, "@320": 320}  # longest side; "" is the main file
QUALITY = 82

BackgroundRemover = Callable[[Image.Image], Image.Image]


class ImageRejected(Exception):
    """The file is not a usable image: retrying won't help (reported as ok=false)."""


@dataclass(frozen=True)
class Processed:
    width: int
    height: int
    files: list[Path]


def _open(src: Path) -> Image.Image:
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(src) as probe:
            if probe.format not in ("JPEG", "PNG", "WEBP"):
                raise ImageRejected(f"unsupported format {probe.format}")
            probe.verify()  # structure check; the image must be opened again afterwards
        im = Image.open(src)
        im.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, SyntaxError) as exc:
        raise ImageRejected(str(exc) or exc.__class__.__name__) from exc
    except OSError as exc:  # truncated or corrupt data
        raise ImageRejected(f"corrupt image: {exc}") from exc
    if im.width * im.height > MAX_PIXELS:
        raise ImageRejected("image too large")
    return im


def process(
    src: Path, out_dir: Path, file_id: str, *, remove_background: bool, remover: BackgroundRemover | None
) -> Processed:
    im = _open(src)
    im = ImageOps.exif_transpose(im)
    if remove_background and remover is not None:
        im = remover(im.convert("RGBA"))
    has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    im = im.convert("RGBA" if has_alpha else "RGB")
    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    main_size = (im.width, im.height)
    for suffix, longest in SIZES.items():
        copy = im.copy()
        copy.thumbnail((longest, longest), Image.Resampling.LANCZOS)  # never upscales
        if suffix == "":
            main_size = copy.size
        target = out_dir / f"{file_id}{suffix}.webp"
        tmp = target.with_suffix(".webp.tmp")
        # No exif/icc_profile/xmp arguments: the new file carries pixels only.
        copy.save(tmp, "WEBP", quality=QUALITY, method=4)
        os.replace(tmp, target)
        files.append(target)
    return Processed(width=main_size[0], height=main_size[1], files=files)


def size_of(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.width, im.height


def rembg_remover() -> BackgroundRemover | None:
    """rembg on the GPU image (model baked in, no download at run time); None when not installed."""
    try:
        from rembg import new_session, remove  # type: ignore[import-not-found]
    except ImportError:
        return None
    session = new_session(os.environ.get("REMBG_MODEL", "u2net"))

    def run(im: Image.Image) -> Image.Image:
        out = remove(im, session=session)
        return out if isinstance(out, Image.Image) else im

    return run
