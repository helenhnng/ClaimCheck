"""SHA-256 fingerprint of ``1. RAW DATA/`` so tests can prove it is never modified."""
from __future__ import annotations

import hashlib
from pathlib import Path

from claimcheck.paths import RAW_DIR

# OS metadata that Finder/Explorer rewrite on their own; not part of the data pack.
IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_raw_data(raw_dir: Path = RAW_DIR) -> dict[str, str]:
    """Map of relative POSIX path -> SHA-256 for every data file under ``raw_dir``."""
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"Raw data folder not found: {raw_dir}")
    return {
        path.relative_to(raw_dir).as_posix(): sha256_file(path)
        for path in sorted(raw_dir.rglob("*"))
        if path.is_file() and path.name not in IGNORED_NAMES
    }
