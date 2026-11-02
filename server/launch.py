"""Safe container entrypoint: preserve state before any server schema migration.

Only hosted Docker/Railway containers use this entrypoint. Windows executables
continue to use server.main directly, never modifying their original data.
"""
import os
from pathlib import Path
from .backup import snapshot_server


def prepare_hosted_start():
    data = Path(os.environ.get("ANKI_COMPANION_DATA", "/data"))
    backups = Path(os.environ.get("ANKI_COMPANION_BACKUPS", "/backups"))
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("ANKI_COMPANION_REQUIRE_PERSISTENT") == "1":
        # A cloud instance must fail closed without BOTH persistent volumes.
        # The SQLite/skin data and its backups must never land in an ephemeral
        # image overlay where replacing the container erases the history.
        for path in (data, backups):
            if not path.is_mount():
                raise RuntimeError(f"Refusing hosted startup: no persistent mount at {path}")
    if os.environ.get("ANKI_COMPANION_REQUIRE_MIGRATION") == "1" and not (data / "companion.sqlite3").is_file():
        raise RuntimeError("Refusing to initialize an empty hosted server: migrate the existing Windows database, pairing token and private skin packs first")
    if (data / "companion.sqlite3").is_file():
        if not backups.is_dir():
            raise RuntimeError("Refusing server update without the persistent backups volume")
        return snapshot_server(data, backups)
    return None


def main():
    path = prepare_hosted_start()
    if path:
        print(f"Verified pre-start state snapshot: {path}", flush=True)
    from .main import main as start_api
    start_api()


if __name__ == "__main__":
    main()
