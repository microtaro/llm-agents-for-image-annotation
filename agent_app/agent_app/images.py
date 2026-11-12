"""Images: stored once by content, imported from server-local files (step 1 design 7)."""

import hashlib
import json
import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .db import encoded, now
from .errors import ApiError, not_found

# An original file read from a folder; uncompressed BMP/PNM can be large.
MAX_SOURCE_BYTES = 256 * 1024 * 1024
# Guards memory: an image is decoded whole for every view (measured 2026-09-29 in
# annotation_server). Pillow's own decompression-bomb limit is aligned to refuse exactly this.
MAX_PIXELS = 100_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
# Pillow's format -> stored extension and media type. PNM covers PPM, PGM and PBM.
IMAGE_FORMATS = {
    "PNG": ("png", "image/png"),
    "JPEG": ("jpg", "image/jpeg"),
    "BMP": ("bmp", "image/bmp"),
    "PPM": ("pnm", "image/x-portable-anymap"),
}
SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".ppm", ".pgm", ".pbm", ".pnm"}


def decode(data: bytes):
    """(shown width, shown height, format) after the header checks; EXIF rotation applied."""
    if len(data) > MAX_SOURCE_BYTES:
        raise ApiError(413, "image_too_large", "Images must be 256 MiB or smaller")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in IMAGE_FORMATS:
                    raise ApiError(
                        422, "invalid_image", "Use PNG, JPEG, BMP or PNM images"
                    )
                if source.size[0] * source.size[1] > MAX_PIXELS:
                    raise ApiError(
                        413, "image_too_large", "Image dimensions exceed the limit"
                    )
                if getattr(source, "n_frames", 1) != 1:
                    raise ApiError(
                        422, "invalid_image", "Animated images are unsupported"
                    )
                shown = ImageOps.exif_transpose(source)
                return shown.size[0], shown.size[1], source.format
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ApiError(
            413, "image_too_large", "Image dimensions exceed the limit"
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise ApiError(422, "invalid_image", "Cannot decode the image") from exc


def store_image(db, data, name, source_path=None, origin=None):
    """The image of these bytes (identical bytes are the same image), adding the source.

    origin: None for a photographed image (real), or {"kind": "generated", "how": {...}}
    for one a program or a model made; the same bytes keep the origin they came with, whatever
    a later import says (definition 52: the origin is the image's own fact)."""
    width, height, kind = decode(data)
    image_id = "img-" + hashlib.sha256(data).hexdigest()
    made = "generated" if origin else "real"
    with db.transaction():
        db.files.put("images", data, IMAGE_FORMATS[kind][0])
        db.execute(
            "INSERT OR IGNORE INTO images(id,name,width,height,byte_size,format,origin,"
            "origin_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                image_id,
                name,
                width,
                height,
                len(data),
                kind,
                made,
                encoded(origin["how"]) if origin else None,
                now(),
            ),
        )
        if source_path:
            db.execute(
                "INSERT OR IGNORE INTO image_sources(image_id,path) VALUES(?,?)",
                (image_id, source_path),
            )
    return image_info(db, image_id)


def _files_of(path: Path):
    """A file, or what a folder holds directly: every entry, said back when not taken (the 50
    images' test 2026-10-29: a README and a folder in it were passed over unsaid, and asked
    what was not taken in, the reception said nothing). Folders in it are not read."""
    if path.is_dir():
        return sorted(path.iterdir())
    return [path]


def scan_paths(paths):
    """What an import of these paths would read, without reading any file's content. A file
    named twice (the same folder given twice) counts once (found 2026-10-05: 50 shown as 100)."""
    files, skipped, seen = [], [], set()
    for raw in paths:
        try:
            base = Path(raw).expanduser().resolve(strict=True)
        except (OSError, ValueError):
            skipped.append({"path": raw, "reason": "not_found"})
            continue
        for path in _files_of(base):
            if str(path) in seen:
                continue
            seen.add(str(path))
            if path.is_dir():
                skipped.append({"path": str(path), "reason": "folder"})
            elif path.suffix.lower() in SUFFIXES:
                files.append({"path": str(path), "name": path.name})
            else:
                skipped.append({"path": str(path), "reason": "invalid_image"})
    return {"files": files, "count": len(files), "skipped": skipped}


def import_paths(db, paths, origin=None):
    """Import server-local files, and the image files directly inside given folders."""
    images, skipped, files = [], [], []
    for raw in paths:
        try:
            base = Path(raw).expanduser().resolve(strict=True)
        except (OSError, ValueError):
            skipped.append({"path": raw, "reason": "not_found"})
            continue
        for path in _files_of(base):
            if path.is_dir():
                skipped.append({"path": str(path), "reason": "folder"})
                continue
            try:
                if path.suffix.lower() not in SUFFIXES:
                    raise ApiError(422, "invalid_image", "Not an image file")
                image = store_image(db, path.read_bytes(), path.name, str(path), origin)
                images.append(image)
                files.append({"path": str(path), "image_id": image["id"]})
            except ApiError as exc:
                skipped.append({"path": str(path), "reason": exc.code})
            except OSError:
                skipped.append({"path": str(path), "reason": "unreadable"})
    return {"images": images, "skipped": skipped, "files": files}


def source_paths(db, image_id):
    """Every file the image (its content) was imported from, in any dataset."""
    return [
        r["path"]
        for r in db.execute(
            "SELECT path FROM image_sources WHERE image_id=? ORDER BY path", (image_id,)
        )
    ]


def image_from(db, path):
    """The image imported from that file, None when none was."""
    return db.one(
        "SELECT i.* FROM image_sources s JOIN images i ON i.id=s.image_id WHERE s.path=?",
        (path,),
    )


def image_row(db, image_id):
    """An image as stored, None when there is none: the one place an image is read by its id
    (fact inventory 9)."""
    return db.one("SELECT * FROM images WHERE id=?", (image_id,))


def image_names(db, image_ids):
    """image id -> its name."""
    if not image_ids:
        return {}
    marks = ",".join("?" * len(image_ids))
    return {
        r["id"]: r["name"]
        for r in db.execute(
            f"SELECT id, name FROM images WHERE id IN ({marks})", tuple(image_ids)
        )
    }


def stored_totals(db):
    """Every image imported, once each (shared by the datasets that use it): how many, bytes."""
    row = db.one("SELECT count(*), coalesce(sum(byte_size), 0) FROM images")
    return {"images": row[0], "bytes": row[1]}


def image_info(db, image_id):
    row = image_row(db, image_id)
    if row is None:
        raise not_found("Image")
    sources = source_paths(db, image_id)
    keys = ("id", "name", "width", "height", "format", "byte_size", "origin")
    how = json.loads(row["origin_json"]) if row["origin_json"] else None
    return {**{k: row[k] for k in keys}, "origin_how": how, "source_paths": sources}


def image_file(db, image_id):
    """The original file's bytes and media type, as imported."""
    info = image_info(db, image_id)
    extension, media_type = IMAGE_FORMATS[info["format"]]
    return db.files.path(
        "images", image_id.removeprefix("img-"), extension
    ).read_bytes(), media_type
