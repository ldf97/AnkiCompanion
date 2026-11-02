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
    components=manifest.get('components') or {
        key:{'version':manifest['version'],'asset':'windows'}
        for key in ('windows_desktop','local_server','anki_desktop_addon')}
    # Enforce that a component is never advertised without its packaged asset.
    if not isinstance(components,dict) or any(
        not isinstance(spec,dict) or spec.get('asset') not in manifest['assets']
        for spec in components.values()):
        raise ValueError('Release components do not match signed assets')
    return dict(configured=True,available=newer,version=manifest['version'],
        build=manifest['build'],commit=manifest['commit'],notes='GitHub signed release',
        filename=name,size=item['size'],sha256=item['sha256'],components=components,
        download_url=PUBLIC_RELEASES+name,
        message='Update available' if newer else 'Up to date')


def component_update_summary(release,remote_server=False):
    '''Show precisely what the Windows Update control can/cannot replace.'''
    components=release.get('components') or {}
    bundled=('windows_desktop','local_server','anki_desktop_addon')
    labels=dict(windows_desktop='Windows desktop',local_server='Local server',
                anki_desktop_addon='Anki desktop add-on',
                android_companion='Android Companion',
                ankidroid_companion='AnkiDroid Companion')
    lines=[]
    for key in bundled:
        if key=='local_server' and remote_server:
            lines.append('Hosted server: updated through Google Cloud deployment, not Windows installer')
        elif key in components or not components:
            lines.append(labels[key]+': included in Windows installer')
    for key in ('android_companion','ankidroid_companion'):
        if key in components:
            lines.append(labels[key]+': separate signed update on the phone')
    return '\n'.join(lines)


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

def preserve_windows_state_before_update(localappdata=None):
    """Automatically snapshot the existing server before replacing binaries.

    This runs inside the GUI Update action; normal upgrades never import or
    restore files. The extra snapshot is for exceptional disaster recovery,
    stored outside the installer code directory and checksum-verified.
    """
    root = Path(localappdata or os.environ.get('LOCALAPPDATA') or
                (Path.home()/'AppData'/'Local'))/'AnkiCompanion'
    data = root/'server'
    if not (data/'companion.sqlite3').is_file():
        return None  # brand-new client or remote-only desktop
    if not (data/'token.txt').is_file():
        raise ValueError('Existing study history has no pairing token; refusing update before data is safe')
    from server.backup import snapshot_server, verify_snapshot
    archive = snapshot_server(data, root/'backups-before-updates')
    if archive is None or 'token.txt' not in verify_snapshot(archive)['files']:
        raise ValueError('Automatic pre-update study backup was not verified')
    return archive


def install(package, release=None):
    """Run a verified GitHub release installer. A paid Authenticode cert is optional.

    This function never runs an arbitrary local executable: the downloader
    verifies the SHA-256 in the official GitHub release manifest, and we
    verify it again before launching the installer.
    """
    package=Path(package).resolve()
    if sys.platform!='win32' or package.suffix.lower()!='.exe':
        raise ValueError('Windows installer required')
    if not release or not release.get('download_url','').startswith(PUBLIC_RELEASES):
        raise ValueError('Only an official verified GitHub Release can be installed')
    if package.name!=release.get('filename'):
        raise ValueError('Installed package does not match release filename')
    if not re.fullmatch(r'[a-f0-9]{64}',release.get('sha256','')):
        raise ValueError('Invalid release checksum')
    if package.stat().st_size!=release.get('size') or hashlib.sha256(package.read_bytes()).hexdigest()!=release['sha256']:
        raise ValueError('Release installer checksum mismatch')
    expected=version().get('windows_signer_thumbprint','')
    if expected:
        # Retain publisher pinning for builds that opted into certificate signing.
        script="$s=Get-AuthenticodeSignature -LiteralPath $env:ANKICOMPANION_INSTALLER; @{status=$s.Status.ToString();thumbprint=$s.SignerCertificate.Thumbprint}|ConvertTo-Json -Compress"
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
            env=dict(os.environ,ANKICOMPANION_INSTALLER=str(package)),check=True,capture_output=True,text=True,timeout=30)
        validate_windows_signature(json.loads(result.stdout),expected)
    # Make a verified, crash-consistent copy of existing reviews, pairing token,
    # and private skin bytes before launching the installer. The normal update
    # leaves the original files in place and never asks for a restore.
    preserve_windows_state_before_update()
    # Windows may still ask for an installer/security confirmation. No shell is
    # required, and the normal installer preserves user data across upgrades.
    subprocess.Popen([str(package),'/CURRENTUSER','/VERYSILENT','/SUPPRESSMSGBOXES',
                      '/NORESTART','/CLOSEAPPLICATIONS','/RESTARTAPPLICATIONS',
                      '/AUTOUPDATE'],close_fds=True)
