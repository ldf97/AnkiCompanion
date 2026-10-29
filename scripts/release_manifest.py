"""Create release metadata from the exact signed binary bytes and source commit."""
from pathlib import Path
import argparse, hashlib, json, re

def make(directory,version,build,commit):
    if not re.fullmatch(r'\d+\.\d+\.\d+',version) or build<1 or not re.fullmatch(r'[a-f0-9]{40}',commit):
        raise ValueError('Use a numeric version, positive build and exact Git commit SHA')
    directory=Path(directory);assets={}
    for platform,name in [('android','AnkiCompanion-Android.apk'),('windows','AnkiCompanion-Windows-Setup.exe'),('source','AnkiCompanion-source.zip')]:
        path=directory/name
        if not path.is_file():raise ValueError('Missing signed release input: '+name)
        raw=path.read_bytes();assets[platform]=dict(filename=name,size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    result=dict(schema_version=1,version=version,build=build,commit=commit,assets=assets)
    (directory/'update.json').write_text(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--version',required=True);p.add_argument('--build',required=True,type=int);p.add_argument('--commit',required=True)
    a=p.parse_args();make(a.directory,a.version,a.build,a.commit)
