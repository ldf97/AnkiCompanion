"""Verify and restore a one-time Google Cloud migration archive.

Never overwrite an existing server database/token, and never unpack unsafe paths.
For a GCE boot script, run as: python3 -m scripts.restore_hosted ARCHIVE DATA_DIRECTORY
"""
from pathlib import Path, PurePosixPath
import hashlib
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
from zipfile import ZipFile
from server.backup import verify_snapshot, SnapshotError


def restore_hosted(archive_file, data_dir):
    archive_file, data = Path(archive_file), Path(data_dir)
    data.mkdir(parents=True, exist_ok=True)
    if (data / "companion.sqlite3").exists() or (data / "token.txt").exists():
        raise SnapshotError("Refusing migration: hosted server already has a database or token")
    if (data / "packs").exists():
        raise SnapshotError("Refusing migration: hosted private skin directory already exists")
    manifest = verify_snapshot(archive_file)
    entries = manifest["files"]
    if "token.txt" not in entries or "companion.sqlite3" not in entries:
        raise SnapshotError("Migration must include original database and pairing token")
    if len(entries) > 10000 or sum(m["size"] for m in entries.values()) > 1_500_000_000:
        raise SnapshotError("Migration archive exceeds safe size limit")
    for name in entries:
        path = PurePosixPath(name)
        if not (name in ("companion.sqlite3", "token.txt")
                or (len(path.parts) >= 4 and path.parts[0] == "packs")):
            raise SnapshotError(f"Unexpected migration member: {name}")
    with tempfile.TemporaryDirectory(prefix=".migration-", dir=data) as temp:
        stage = Path(temp)
        with ZipFile(archive_file) as archive:
            token = archive.read("token.txt").decode("utf-8").strip()
            if len(token) < 16:
                raise SnapshotError("Invalid original pairing token")
            for member in archive.infolist():
                if member.filename == "manifest.json":
                    continue
                if stat.S_ISLNK(member.external_attr >> 16) or member.is_dir():
                    raise SnapshotError("Migration cannot contain links or directory entries")
                dest = stage.joinpath(*PurePosixPath(member.filename).parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, dest.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        with sqlite3.connect(f"file:{(stage / 'companion.sqlite3').as_posix()}?mode=ro", uri=True) as check:
            integrity = check.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise SnapshotError("Original review database failed integrity check")
            settings = check.execute("SELECT value FROM meta WHERE key='settings'").fetchone()
            if not settings:
                raise SnapshotError("Original study settings missing from database")
        # Database is installed LAST. A failed earlier write cannot cause a
        # new server to silently boot without its original private skin/token.
        if (stage / "packs").exists():
            os.replace(stage / "packs", data / "packs")
        os.replace(stage / "token.txt", data / "token.txt")
        try:
            (data / "token.txt").chmod(0o600)
            os.replace(stage / "companion.sqlite3", data / "companion.sqlite3")
        except Exception:
            # A partial first migration must not be mistaken for a completed
            # server; its recovery is intentionally manual/fail-closed.
            raise
    return manifest


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python3 -m scripts.restore_hosted ARCHIVE DATA_DIR")
    result = restore_hosted(sys.argv[1], sys.argv[2])
    print(f"Verified one-time Google Cloud migration: {len(result['files'])} preserved files")


if __name__ == "__main__":
    main()
