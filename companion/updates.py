from pathlib import Path
import hashlib, json, sys, os, subprocess, urllib.request, re

ROOT=Path(__file__).resolve().parents[1]
def version():return json.loads((ROOT/'VERSION.json').read_text())

PUBLIC_RELEASES='https://github.com/ldf97/AnkiCompanion/releases/latest/download/'

def github_release(platform='windows'):
    """Poll published GitHub assets even without the local API server."""
    import urllib.error
    installed=version()
    try:
        req=urllib.request.Request(PUBLIC_RELEASES+'update.json',
            headers={'User-Agent':'AnkiCompanion/1.0'})
        with urllib.request.urlopen(req,timeout=20) as response:
            assert response.geturl().startswith('https://'), 'Insecure release redirect'
            raw=response.read(128*1024+1)
        if len(raw)>128*1024:raise ValueError('Release manifest too large')
        manifest=json.loads(raw)
    except urllib.error.HTTPError as exc:
        if exc.code==404:return dict(configured=True,available=False,message='No stable signed release has been published')
        raise
    if manifest.get('schema_version')!=1 or not re.fullmatch(r'\d+\.\d+\.\d+',manifest.get('version','')):
        raise ValueError('Invalid GitHub release version')
    item=manifest.get('assets',{}).get(platform)
    if not item:return dict(configured=True,available=False,message='Release has no Windows package')
    name=item.get('filename','')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.exe',name) or not re.fullmatch(r'[a-f0-9]{64}',item.get('sha256','')):
        raise ValueError('Invalid signed update metadata')
    if not 0<item.get('size',0)<=500*1024*1024:raise ValueError('Invalid signed update size')
    current=tuple(int(x) for x in installed['version'].split('.'))
    newer=tuple(int(x) for x in manifest['version'].split('.'))>current
    return dict(configured=True,available=newer,version=manifest['version'],
        build=manifest['build'],commit=manifest['commit'],notes='GitHub signed release',
        filename=name,size=item['size'],sha256=item['sha256'],
        download_url=PUBLIC_RELEASES+name,
        message='Update available' if newer else 'Up to date')


def download(client,release,directory):
    if not release.get('available'):raise ValueError('No update is available')
    name=release['filename']
    if Path(name).name!=name or not name.lower().endswith(('.exe','.zip')):raise ValueError('Invalid update filename')
    dest=Path(directory)/name;dest.parent.mkdir(parents=True,exist_ok=True);temp=dest.with_suffix('.partial')
    if 'download_url' in release:
        url=release['download_url']
        if not url.startswith(PUBLIC_RELEASES):raise ValueError('Untrusted update URL')
        request=urllib.request.Request(url,headers={'User-Agent':'AnkiCompanion/1.0'})
        opener=urllib.request.build_opener()
    else:
        request=urllib.request.Request(client.url+release['download_path'],headers={'Authorization':'Bearer '+client.token})
        opener=client.opener
    digest=hashlib.sha256();size=0
    try:
        with opener.open(request,timeout=60) as source,temp.open('wb') as target:
            if 'download_url' in release and not source.geturl().startswith('https://'):
                raise ValueError('Insecure update redirect')
            while chunk:=source.read(1024*1024):
                size+=len(chunk)
                if size>release['size'] or size>500*1024*1024:raise ValueError('Update size mismatch')
                digest.update(chunk);target.write(chunk)
        if size!=release['size'] or digest.hexdigest()!=release['sha256']:raise ValueError('Update checksum mismatch')
        temp.replace(dest);return dest
    finally:temp.unlink(missing_ok=True)

def validate_windows_signature(signature, expected):
    if not re.fullmatch(r'[A-Fa-f0-9]{40}',expected or ''):
        raise ValueError('This development build has no trusted Windows publisher configured. Install a signed release manually first.')
    if signature.get('status')!='Valid' or signature.get('thumbprint','').upper()!=expected.upper():
        raise ValueError('Windows installer signature does not match the trusted publisher')

def install(package):
    package=Path(package).resolve()
    if sys.platform=='win32' and package.suffix.lower()=='.exe':
        # Pass the path through an environment value, never interpolate it as code.
        script="$s=Get-AuthenticodeSignature -LiteralPath $env:ANKICOMPANION_INSTALLER; @{status=$s.Status.ToString();thumbprint=$s.SignerCertificate.Thumbprint}|ConvertTo-Json -Compress"
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
            env=dict(os.environ,ANKICOMPANION_INSTALLER=str(package)),check=True,capture_output=True,text=True,timeout=30)
        validate_windows_signature(json.loads(result.stdout),version().get('windows_signer_thumbprint',''))
        subprocess.Popen([str(package),'/CURRENTUSER','/RESTARTAPPLICATIONS'],close_fds=True)
        return
    raise ValueError('Automatic installation is available for the Windows installer. Use the source package on this platform.')
