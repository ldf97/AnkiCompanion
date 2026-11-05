"""Entry point for the bundled server and safe pre-update snapshot helper."""
import os
import sys
from pathlib import Path

def backup_before_update():
    from server.backup import snapshot_server, verify_snapshot
    root=Path(os.environ.get('LOCALAPPDATA') or (Path.home()/'AppData'/'Local'))/'AnkiCompanion'
    data=root/'server'
    if not (data/'companion.sqlite3').exists():
        return  # Fresh install; nothing to preserve.
    if not (data/'token.txt').is_file():
        raise RuntimeError('Existing study data is missing its pairing token; update aborted')
    backup=snapshot_server(data,root/'backups-before-updates')
    if backup is None or 'token.txt' not in verify_snapshot(backup)['files']:
        raise RuntimeError('Pre-update study backup failed verification')

if __name__=='__main__':
    if len(sys.argv)==2 and sys.argv[1]=='--backup-before-update':
        backup_before_update()
    else:
        from server.main import main
        main()
