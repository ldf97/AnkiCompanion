"""Create an atomic source checkpoint, including every saved test result."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib, json

root = Path(__file__).resolve().parents[1]
destination = root.parent / 'deliverables'
destination.mkdir(exist_ok=True)
archive = destination / 'AnkiCompanion-checkpoint.zip'
temporary = archive.with_suffix('.zip.tmp')
excluded = {'.git', '.kotlin', '.gradle', '.venv', '__pycache__', '.pytest_cache', 'build', 'data', '.signing', 'node_modules', 'dist'}
files = sorted(p for p in root.rglob('*') if p.is_file()
               and not (set(p.relative_to(root).parts) & excluded)
               and p.suffix.lower() not in {'.jks', '.keystore', '.pfx', '.p12', '.key'}
               and not p.name.startswith('.env')
               and p.name not in {'token.txt', 'connection.json', 'local.properties', 'checkpoint-manifest.json'})
manifest = {p.relative_to(root).as_posix(): {'bytes': p.stat().st_size,
             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files}
with ZipFile(temporary, 'w', ZIP_DEFLATED) as zipfile:
    for p in files:
        zipfile.write(p, 'AnkiCompanion/' + p.relative_to(root).as_posix())
    zipfile.writestr('AnkiCompanion/checkpoint-manifest.json', json.dumps(manifest, indent=2))
with ZipFile(temporary) as zipfile:
    failure = zipfile.testzip()
    if failure:
        raise RuntimeError('ZIP integrity failure: ' + failure)
temporary.replace(archive)
print(json.dumps({'path': str(archive), 'bytes': archive.stat().st_size,
                  'files': len(files), 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}))
