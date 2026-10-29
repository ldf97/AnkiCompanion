"""Allowlisted source export; fail closed on private artwork or quote matches."""
from pathlib import Path
import json, hashlib, shutil, zipfile
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT.parent/'public-source'

def export():
    roots=['app','companion','server','desktop','anki_addon','android','fonts','assets','skins/study_companion','tests','scripts','deployment','installer','.github']
    files={p for directory in roots for p in (ROOT/directory).rglob('*') if p.is_file()}
    files.update(ROOT/p for p in ['VERSION.json','.gitignore','requirements-server.txt','requirements-desktop.txt','requirements-test.txt'])
    ignored={'build','.gradle','__pycache__','.pytest_cache','local.properties'}
    files={p for p in files if not(set(p.relative_to(ROOT).parts)&ignored) and p.suffix not in {'.pyc','.jks','.key','.pfx','.keystore'}}
    files={p for p in files if p.parent!=ROOT/'app' or p.name in {'__init__.py','widget_engine.py','skin_packs.py'}}
    private=ROOT/'skins/eren_anki';phrases=[];private_hashes=set()
    if private.exists():
        skin=json.loads((private/'skin.json').read_text())
        phrases=[q['text'].encode() for slot in skin['time_slots']+[skin['completion']] for q in slot['quotes']]
        private_hashes={hashlib.sha256(p.read_bytes()).hexdigest() for p in private.rglob('*') if p.suffix.lower() in {'.png','.jpg','.jpeg','.webp'}}
    if DEST.exists():shutil.rmtree(DEST)
    DEST.mkdir()
    manifest={}
    for p in sorted(files):
        raw=p.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        assert digest not in private_hashes,f'Private artwork: {p}'
        assert not any(q in raw for q in phrases),f'Private quote: {p}'
        rel=p.relative_to(ROOT);dest=DEST/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        manifest[str(rel)]=digest
    public_readme=(ROOT/'PUBLIC_README.md').read_text()
    for name in ['README.md','WORK_MODE_START_HERE.md','MAINTENANCE_HANDOFF.md']:(DEST/name).write_text(public_readme)
    (DEST/'PUBLIC_SOURCE_NOTICE.md').write_text('Personal artwork, quotes, credentials, test user data and private checkpoints are excluded. Original personal assets remain in the private continuation. Public builds use an independent neutral skin.\n')
    out=ROOT.parent/'deliverables';out.mkdir(exist_ok=True)
    with zipfile.ZipFile(out/'AnkiCompanion-public-source.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(DEST.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(DEST))
    (ROOT/'test-results/public-export-audit.json').write_text(json.dumps(dict(files=len(manifest),private_artwork_matches=0,private_quote_matches=0,sha256=manifest),indent=2))
    print(json.dumps(dict(directory=str(DEST),files=len(manifest)+4,private_artwork_matches=0,private_quote_matches=0)))
    return DEST
if __name__=='__main__':export()
