"""Consistent, verified server snapshots before hosted container replacement.

The repository never contains private skin assets, tokens or study history.
Snapshots live in a separate, persistent, operator-controlled Docker volume.
This is a backup, not a replacement for a provider-level off-host backup.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED


class SnapshotError(RuntimeError):
    pass


def _digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_server(data_dir, backups_dir):
    data, backups = Path(data_dir), Path(backups_dir)
    source = data / "companion.sqlite3"
    # A virgin installation has no records to preserve.
    if not source.is_file():
        return None
    backups.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".snapshot-source-", dir=backups) as temp:
        stage = Path(temp)
        copied = stage / "companion.sqlite3"
        # sqlite3.backup() includes committed WAL transactions; copying a live
        # .sqlite3 file alone would silently lose recent answers.
        with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=30) as active:
            with sqlite3.connect(copied) as saved:
                active.backup(saved)
                result = saved.execute("PRAGMA integrity_check").fetchone()
                if result is None or result[0] != "ok":
                    raise SnapshotError("SQLite snapshot failed integrity check")
        entries = {"companion.sqlite3": copied}
        token = data / "token.txt"
        if token.is_symlink():
            raise SnapshotError("Refusing to snapshot a symlinked server token")
        if token.is_file():
            entries["token.txt"] = token
        packs = data / "packs"
        if packs.is_symlink():
            raise SnapshotError("Refusing to snapshot a symlinked skin directory")
        if packs.is_dir():
            for file in sorted(packs.rglob("*")):
                if file.is_symlink():
                    raise SnapshotError("Refusing to snapshot symlinked skin data")
                if not file.is_file():
                    continue
                entries[file.relative_to(data).as_posix()] = file
        if len(entries) > 10000:
            raise SnapshotError("Unexpectedly large skin collection")
        manifest = {"schema": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
                    "files": {name: {"sha256": _digest_file(file), "size": file.stat().st_size}
                              for name, file in sorted(entries.items())}}
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = backups / f"server-{stamp}-{secrets.token_hex(4)}.zip"
        with tempfile.NamedTemporaryFile(prefix=".snapshot-", suffix=".partial",
                                         dir=backups, delete=False) as handle:
            partial = Path(handle.name)
        try:
            os.chmod(partial, 0o600)
            with ZipFile(partial, "w", compression=ZIP_DEFLATED, allowZip64=True) as archive:
                for name, file in sorted(entries.items()):
                    archive.write(file, name)
                archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
            verify_snapshot(partial)
            os.replace(partial, dest)
            return dest
        finally:
            partial.unlink(missing_ok=True)


def verify_snapshot(archive_path):
    with ZipFile(archive_path, "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise SnapshotError("Malformed snapshot archive")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("schema") != 1 or "companion.sqlite3" not in manifest.get("files", {}):
            raise SnapshotError("Missing required SQLite snapshot")
        if set(names) != set(manifest["files"]) | {"manifest.json"}:
            raise SnapshotError("Snapshot file list differs from manifest")
        for name, meta in manifest["files"].items():
            if name.startswith("/") or "\\" in name or ".." in Path(name).parts:
                raise SnapshotError("Unsafe snapshot file path")
            digest = hashlib.sha256()
            size = 0
            with archive.open(name) as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    size += len(chunk)
                    digest.update(chunk)
            if size != meta["size"] or digest.hexdigest() != meta["sha256"]:
                raise SnapshotError(f"Snapshot checksum failed for {name}")
        return manifest


def main():
    parser = argparse.ArgumentParser(description="Verify or create a server-state backup")
    parser.add_argument("command", choices=["snapshot", "verify"])
    parser.add_argument("--data", default="/data")
    parser.add_argument("--backups", default="/backups")
    parser.add_argument("--archive")
    args = parser.parse_args()
    if args.command == "verify":
        if not args.archive:
            parser.error("verify requires --archive")
        result = verify_snapshot(args.archive)
        print(f"Verified {len(result['files'])} preserved files")
    else:
        result = snapshot_server(args.data, args.backups)
        print("New server: nothing to back up" if result is None else f"Verified backup: {result}")


if __name__ == "__main__":
    main()
