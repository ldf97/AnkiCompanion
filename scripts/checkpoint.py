"""Create an atomic source checkpoint, including every saved test result."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib, json, os
from contextlib import contextmanager

root = Path(__file__).resolve().parents[1]
destination = root.parent / 'deliverables'
destination.mkdir(exist_ok=True)
@contextmanager
def checkpoint_lock():
    # Test runners may finish together. Serialize writers to the atomic archive.
    with (destination/'.checkpoint.lock').open('a+b') as lock:
        if os.name=='nt':
            import msvcrt
            lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
            msvcrt.locking(lock.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX)
        try:yield
        finally:
            if os.name=='nt':lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(lock,fcntl.LOCK_UN)

archive = destination / 'AnkiCompanion-checkpoint.zip' 
temporary = archive.with_suffix('.zip.tmp')
excluded = {'.git', '.kotlin', '.gradle', '.venv', '__pycache__', '.pytest_cache', 'build', 'data', '.signing', 'node_modules', 'dist'}
files = sorted(p for p in root.rglob('*') if p.is_file()
               and not (set(p.relative_to(root).parts) & excluded)
               and p.suffix.lower() not in {'.jks', '.keystore', '.pfx', '.p12', '.key'}
               and not p.name.startswith('.env')
               and p.name not in {'token.txt', 'connection.json', 'local.properties', 'checkpoint-manifest.json'})
with checkpoint_lock():
    manifest={}
    with ZipFile(temporary, 'w', ZIP_DEFLATED) as zipfile:
        for p in files:
            # Hash the same bytes written to the ZIP, even when a test log is growing.
            raw=p.read_bytes();name=p.relative_to(root).as_posix()
            manifest[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            zipfile.writestr('AnkiCompanion/'+name,raw)
        zipfile.writestr('AnkiCompanion/checkpoint-manifest.json',json.dumps(manifest,indent=2))
    with ZipFile(temporary) as zipfile:
        failure=zipfile.testzip()
        if failure:raise RuntimeError('ZIP integrity failure: '+failure)
    temporary.replace(archive)
    print(json.dumps({'path':str(archive),'bytes':archive.stat().st_size,
        'files':len(files),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}))
