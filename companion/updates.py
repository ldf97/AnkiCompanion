from pathlib import Path
import hashlib, json, sys, os, subprocess, urllib.request, re

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
