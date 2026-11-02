"""Create release metadata from the exact signed binary bytes and source commit."""
from pathlib import Path
import argparse, hashlib, json, re

def make(directory,version,build,commit):
    if not re.fullmatch(r'\d+\.\d+\.\d+',version) or build<1 or not re.fullmatch(r'[a-f0-9]{40}',commit):
        raise ValueError('Use a numeric version, positive build and exact Git commit SHA')
    directory=Path(directory);assets={}
    for platform,name in [('android','AnkiCompanion-Android.apk'),('ankidroid','AnkiDroid-Companion-Android.apk'),('windows','AnkiCompanion-Windows-Setup.exe'),('source','AnkiCompanion-source.zip')]:
        path=directory/name
        if not path.is_file():
            # Requirement #30 is an ALL-component release, not a misleading
            # Windows-only release that silently omits an installed Android app.
            # The signing workflow must build both compatible production APKs.
            raise ValueError('Missing required signed release input: '+name)
        raw=path.read_bytes();assets[platform]=dict(filename=name,size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        if platform=='android': assets[platform]['version_code']=build
        if platform=='ankidroid': assets[platform]['version_code']=220000000+build
    # One release can contain multiple independently installed components.
    # Desktop, local server and Anki add-on share ONE Windows installer; the
    # two Android package IDs are independent system-managed updates.
    components={
        'windows_desktop':{'version':version,'asset':'windows'},
        'local_server':{'version':version,'asset':'windows'},
        'anki_desktop_addon':{'version':version,'asset':'windows'},
    }
    if 'android' in assets:
        components['android_companion']={'version':version,'asset':'android'}
    if 'ankidroid' in assets:
        components['ankidroid_companion']={'version':version,'asset':'ankidroid'}
    result=dict(schema_version=1,version=version,build=build,commit=commit,
                assets=assets,components=components)
    (directory/'update.json').write_text(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--version',required=True);p.add_argument('--build',required=True,type=int);p.add_argument('--commit',required=True)
    a=p.parse_args();make(a.directory,a.version,a.build,a.commit)