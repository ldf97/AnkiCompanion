"""Stamp packaged Anki add-on with the exact, already-approved release version.

Only runs in GitHub candidate builds. Existing installed profiles and add-on
configurations are never touched.
"""
import argparse
import json
from pathlib import Path
import re


def stamp(version, root=None):
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):
        raise ValueError('Expected numeric major.minor.patch release version')
    repo=Path(root or Path(__file__).resolve().parents[1])
    path=repo/'anki_addon'/'manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('package')!='anki_companion_bridge':
        raise ValueError('Unexpected add-on identity; refusing to stamp')
    manifest['version']=version
    temporary=path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(path)
    return version


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--version',required=True)
    args=p.parse_args();print('Anki add-on version',stamp(args.version))