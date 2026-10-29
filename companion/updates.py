from pathlib import Path
import hashlib, json, sys, os, subprocess, urllib.request

ROOT=Path(__file__).resolve().parents[1]
def version():return json.loads((ROOT/'VERSION.json').read_text())

def download(client,release,directory):
    if not release.get('available'):raise ValueError('No update is available')
    name=release['filename']
    if Path(name).name!=name or not name.lower().endswith(('.exe','.zip')):raise ValueError('Invalid update filename')
    dest=Path(directory)/name;dest.parent.mkdir(parents=True,exist_ok=True);temp=dest.with_suffix('.partial')
    request=urllib.request.Request(client.url+release['download_path'],headers={'Authorization':'Bearer '+client.token})
    digest=hashlib.sha256();size=0
    try:
        with client.opener.open(request,timeout=60) as source,temp.open('wb') as target:
            while chunk:=source.read(1024*1024):
                size+=len(chunk)
                if size>release['size'] or size>500*1024*1024:raise ValueError('Update size mismatch')
                digest.update(chunk);target.write(chunk)
        if size!=release['size'] or digest.hexdigest()!=release['sha256']:raise ValueError('Update checksum mismatch')
        temp.replace(dest);return dest
    finally:temp.unlink(missing_ok=True)

def install(package):
    package=Path(package)
    if sys.platform=='win32' and package.suffix.lower()=='.exe':
        subprocess.Popen([str(package),'/CURRENTUSER','/RESTARTAPPLICATIONS'],close_fds=True)
        return
    raise ValueError('Automatic installation is available for the Windows installer. Use the source package on this platform.')
