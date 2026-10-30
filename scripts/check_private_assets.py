"""Compare every original personal skin byte against the authoritative input ZIP."""
from pathlib import Path
from zipfile import ZipFile
import sys,json,hashlib
root=Path(__file__).resolve().parents[1]
with ZipFile(sys.argv[1]) as z:
    candidates=[n for n in z.namelist() if n.endswith('skins/eren_anki/skin.json')]
    if not candidates:raise RuntimeError('Original private skin manifest not found')
    prefix=min(candidates,key=lambda x:len(Path(x).parts)).removesuffix('skin.json')
    rows=[]
    for name in z.namelist():
        if not name.startswith(prefix) or name.endswith('/'):continue
        relative=name[len(prefix):];target=root/'skins/eren_anki'/relative
        before=z.read(name);after=target.read_bytes()
        if before!=after:raise AssertionError('Original personal asset changed: '+relative)
        rows.append(dict(path='skins/eren_anki/'+relative,bytes=len(after),sha256=hashlib.sha256(after).hexdigest()))
(root/'test-results/private-asset-integrity.json').write_text(json.dumps(dict(result='PASS',unchanged_files=len(rows),files=rows),indent=2))
print('PASS:',len(rows),'original private skin files are byte-for-byte unchanged')
