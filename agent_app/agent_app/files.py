"""Content-addressed files next to the database: images, masks and sheets, named by SHA-256.

Images keep their original format, so the extension varies; masks are PNG; sheets are JPEG.
"""

import hashlib
import os
import tempfile
from pathlib import Path

KINDS = ("images", "masks", "sheets")


def files_root(db_path):
    """<db dir>/<db name without .db>-files, so a test database gets its own files."""
    path = Path(db_path)
    return path.with_name(path.stem + "-files")


class Files:
    def __init__(self, root):
        self.root = Path(root)

    def path(self, kind, sha256, ext="png"):
        if kind not in KINDS:
            raise ValueError("Unknown file kind")
        return self.root / kind / sha256[:2] / f"{sha256}.{ext}"

    def stored(self, kind, sha256):
        """Files of these bytes, whatever the extension; temporary .part files never match."""
        return list(self.path(kind, sha256).parent.glob(f"{sha256}.*"))

    def find(self, kind, sha256):
        found = self.stored(kind, sha256)
        if not found:
            raise FileNotFoundError(self.path(kind, sha256))
        return found[0]

    def put(self, kind, data, ext="png"):
        """Store bytes once; a crash never leaves a partial file under the final name."""
        sha256 = hashlib.sha256(data).hexdigest()
        target = self.path(kind, sha256, ext)
        if target.exists():
            return sha256
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=target.parent, suffix=".part")
        try:
            with os.fdopen(handle, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        return sha256

    def read(self, kind, sha256):
        return self.find(kind, sha256).read_bytes()

    def remove(self, kind, sha256):
        for path in self.stored(kind, sha256):
            path.unlink(missing_ok=True)

    def usage(self, kind):
        """(files, bytes) of one kind, measured on disk."""
        sizes = [
            p.stat().st_size
            for p in (self.root / kind).glob("*/*")
            if p.suffix != ".part"
        ]
        return len(sizes), sum(sizes)
