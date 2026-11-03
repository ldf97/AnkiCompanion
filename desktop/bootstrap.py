"""Self-contained Windows bootstrap. Run automatically by the GUI.

Personal installers include the verified original Eren pack beside their app
binary, so the owner never has to find, import or select it manually. Public
source builds use a complete neutral fallback and still support skin uploads.
"""
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen
from zipfile import ZipFile, BadZipFile
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

from companion.transport import Client
from companion.ports import LOCAL_URL, migrate_local_url

EREN_SHA256 = "7c25d1434b9971ea89193be60a665b18c0a5ed9be66fa4f92c36c94752dce412"
CLOUDFLARED_SHA256 = "547057326266f0e1c7d50d102dbd22ff283d740c055bd61e94f10e2c606f89af"
PAIRING_HOST = re.compile(r"^https://[a-z0-9-]+\.trycloudflare\.com$")

def has_remote_connection(config):
    """Keep an explicitly configured remote connection on Windows restarts.

    Running a local bootstrap must never replace the saved hosted endpoint,
    token, or collection preferences. A trusted LAN connection may use HTTP;
    public remote connections must be HTTPS.
    """
    if not isinstance(config, dict) or len(config.get("token") or "") < 16:
        return False
    try:
        url = urlsplit((config.get("url") or "").strip())
        return (bool(url.hostname)
                and url.hostname not in ("localhost", "127.0.0.1", "::1")
                and not (url.username or url.password or url.query or url.fragment)
                and (url.scheme == "https" or
                     (url.scheme == "http" and config.get("allow_lan_http") is True)))
    except (ValueError, TypeError):
        return False


def remote_pairing_link(config):
    """Produce a phone pairing link from the *saved* always-on HTTPS server."""
    if not has_remote_connection(config) or urlsplit(config["url"]).scheme != "https":
        raise ValueError("Remote phone pairing requires a configured HTTPS server")
    base = config["url"].rstrip("/")
    return base + "?" + urlencode({"token": config["token"], "collection_id": "primary"})



def data_dir():
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "AnkiCompanion" / "server"


def server_executable():
    base = Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False):
        return base.parent / "server" / "AnkiCompanionServer.exe"
    return base / "AnkiCompanionServer.exe"


def hidden_process(args, **kwargs):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    return subprocess.Popen(args, creationflags=flags, close_fds=True, **kwargs)


def _healthy(url=LOCAL_URL, timeout=1.5):
    try:
        with urlopen(url + "/health", timeout=timeout) as response:
            return response.status == 200 and b'"ok"' in response.read(256)
    except (OSError, ValueError):
        return False


def retire_legacy_windows_server():
    """Retire only our authenticated *old* process, never AnkiConnect or unrelated PIDs.

    An existing 8765 listener is not evidence of our process: AnkiConnect uses
    that port. Require companion API authentication with this installation's
    token and an executable-path match before Windows terminates anything.
    This is invoked by the app's repair/startup flow, not the user's shell.
    """
    if sys.platform != 'win32':
        return False
    token_path = data_dir() / 'token.txt'
    if not token_path.is_file():
        return False
    token = token_path.read_text(encoding='utf-8').strip()
    if len(token) < 16:
        return False
    try:
        Client('http://127.0.0.1:8765', token).request('/v1/state')
    except Exception:
        return False  # AnkiConnect or no old companion server
    exe = server_executable().resolve()
    if not exe.is_file():
        raise RuntimeError('An old Companion server is using AnkiConnect port 8765, but its installed executable cannot be located')
    script = ("$p=[IO.Path]::GetFullPath($env:ANKICOMPANION_SERVER_BIN); "
              "$found=@(Get-CimInstance Win32_Process -Filter \"Name='AnkiCompanionServer.exe'\" | "
              "Where-Object { $_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath) -ieq $p }); "
              "if ($found.Count -ne 1) { exit 3 }; "
              "$found | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop }")
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                            env={**os.environ,'ANKICOMPANION_SERVER_BIN':str(exe)},
                            capture_output=True,text=True,timeout=20)
    if result.returncode != 0:
        raise RuntimeError('The old AnkiCompanion server still occupies AnkiConnect port 8765; use Repair Setup after closing the old server')
    for _ in range(20):
        try:
            Client('http://127.0.0.1:8765',token).request('/v1/state')
        except Exception:
            return True
        time.sleep(0.2)
    raise RuntimeError('The old companion server has not released port 8765')


def ensure_server():
    """Start packaged server when it is missing, keeping the same token/data."""
    home = data_dir()
    retire_legacy_windows_server()
    if not _healthy():
        executable = server_executable()
        if not executable.is_file():
            raise RuntimeError("The AnkiCompanion Server component is missing from this installation")
        hidden_process([str(executable)], cwd=str(executable.parent),
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        for _ in range(48):
            if _healthy(timeout=.5):
                break
            time.sleep(.25)
    if not _healthy():
        raise RuntimeError("Companion server did not start. Please use the app's Connection button for details")
    token_path = home / "token.txt"
    if not token_path.is_file():
        raise RuntimeError("Companion server did not generate its pairing token")
    token = token_path.read_text(encoding="utf-8").strip()
    if len(token) < 16:
        raise RuntimeError("Companion server generated an invalid pairing token")
    client = Client(LOCAL_URL, token)
    client.request("/v1/state")
    return token


def _private_candidates():
    """Find the verified pack in the actual installer FIRST, then older bundles.

    No filesystem crawl: packaged art is always in the app installation and
    user-provided legacy bundles are checked only in predictable locations.
    """
    home = Path.home()
    executable = Path(sys.executable).resolve()
    install_root = executable.parent.parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    directories = [install_root / "skins", install_root / "packages", install_root,
                   home / "Downloads", home / "Desktop", home / "Documents",
                   data_dir(), Path(os.environ.get("USERPROFILE", str(home))) / "Downloads"]
    patterns = ("Eren-Anki-Private-Skin-1.0.0.zip",
                "AnkiCompanion*Eren*.zip",
                "AnkiCompanion*Personal*.zip",
                "AnkiCompanion*Connection*Repair*.zip",
                "AnkiCompanion*Updated*.zip")
    seen = set()
    for folder in directories:
        if not folder.is_dir():
            continue
        for pattern in patterns:
            for path in folder.glob(pattern):
                if path.is_file() and path not in seen and path.stat().st_size < 300_000_000:
                    seen.add(path)
                    yield path
        for path in folder.glob("AnkiCompanion*/Windows/Eren-Anki-Private-Skin-1.0.0.zip"):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def _verified_skin(data):
    return len(data) < 52_000_000 and hashlib.sha256(data).hexdigest() == EREN_SHA256


def find_original_eren():
    for path in _private_candidates():
        try:
            if path.name == "Eren-Anki-Private-Skin-1.0.0.zip":
                value = path.read_bytes()
                if _verified_skin(value):
                    return value
            else:
                with ZipFile(path) as archive:
                    names = [name for name in archive.namelist()
                             if name.endswith("/Eren-Anki-Private-Skin-1.0.0.zip")
                             or name == "Eren-Anki-Private-Skin-1.0.0.zip"]
                    for name in names:
                        info = archive.getinfo(name)
                        if info.file_size > 52_000_000:
                            continue
                        value = archive.read(name)
                        if _verified_skin(value):
                            return value
        except (BadZipFile, OSError, RuntimeError, ValueError):
            continue
    return None


def recover_eren(client):
    """Provision Eren as the personal install default exactly once.

    New personal installs have the original ZIP within the installer; Android
    subsequently receives that very same pack from the authenticated server.
    Subsequent custom skin choices must never be reset at app restart/update.
    """
    installed = client.request("/v1/skins")
    exists = any(s["id"] == "eren_anki" and s["version"] == "1.0.0"
                 for s in installed.get("skins", []))
    if not exists:
        data = find_original_eren()
        if data is None:
            return "Eren is unavailable: this installer contains no verified Eren skin; upload remains available"
        imported = client.request("/v1/skins/import", "POST", data,
                                  content_type="application/zip")
        if imported.get("id") != "eren_anki" or imported.get("version") != "1.0.0":
            raise RuntimeError("The verified Eren skin was rejected by the server")

    # Old installs may have imported the art without selecting it. Mark the
    # one-time selection, so choosing another skin later remains authoritative.
    marker = data_dir() / ".personal-eren-default-selected"
    if marker.exists():
        return "Eren artwork available; selected skin preserved"
    settings = client.request("/v1/settings")
    if settings.get("skin_id") in (None, "", "study_companion"):
        updated = dict(settings, skin_id="eren_anki", skin_version="1.0.0")
        client.request("/v1/settings", "PUT", updated)
        result = "Eren artwork activated by default"
    else:
        result = "Eren artwork available; selected skin preserved"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("Personal skin default provisioned; do not reset user skin choices.\n", encoding="utf-8")
    return result


def addon_archive():
    if getattr(sys,'frozen',False):
        return Path(sys.executable).resolve().parent.parent/'Anki_Companion_Bridge.ankiaddon'
    return Path(__file__).resolve().parents[1]/'packages'/'Anki_Companion_Bridge.ankiaddon'


ADDON_SOURCE_FILES=frozenset({'__init__.py','bridge.py','history.py','rules.py',
                 'transport.py','review_epoch.py','config.json','config.md','manifest.json'})


def ensure_anki_bridge():
    """Safely install/upgrade the optional desktop add-on without scripting.

    Never read, modify, copy, or replace Anki's collection files. Preserve
    meta.json and any user's existing add-on configuration/preferences.
    """
    roaming=os.environ.get('APPDATA')
    if not roaming:return 'Anki profile directory not available yet'
    base=Path(roaming)/'Anki2'
    if not base.is_dir():return 'Anki not installed yet; will retry next startup'
    archive=addon_archive()
    if not archive.is_file():return 'Anki bridge package was not bundled'
    addons=base/'addons21';addons.mkdir(exist_ok=True)
    target=addons/'anki_companion_bridge'
    with ZipFile(archive) as z:
        names=z.namelist()
        allowed=ADDON_SOURCE_FILES
        if set(names)!=allowed or any(z.getinfo(n).file_size>250_000 for n in names):
            raise ValueError('Bundled desktop bridge did not pass validation')
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('package')!='anki_companion_bridge':
            raise ValueError('Unexpected add-on package identity')
        files={n:z.read(n) for n in names}
    # Detect an old, differently-named instance of OUR bridge. Do not install
    # a duplicate that would register hooks twice and disrupt Anki.
    for candidate in addons.iterdir():
        if not candidate.is_dir() or candidate==target:continue
        info=candidate/'manifest.json'
        try:
            if info.is_file() and json.loads(info.read_text(encoding='utf-8')).get('package')=='anki_companion_bridge':
                target=candidate;break
        except (OSError,ValueError):pass
    target.mkdir(exist_ok=True)
    # Do not overwrite the user's saved pairing token, deck preferences, or
    # manual settings with a bundled default on each automatic repair.
    configured = target/'config.json'
    if configured.is_file():
        try:
            existing=json.loads(configured.read_text(encoding='utf-8'))
            if isinstance(existing,dict):
                existing['server_url']=migrate_local_url(existing.get('server_url'))
                files['config.json']=json.dumps(existing,indent=2).encode('utf-8')
        except (OSError,ValueError):
            pass
    # Anki persists overrides in meta.json, independently of config.json.
    # Migrate ONLY the legacy loopback URL, retaining every other preference.
    meta=target/'meta.json'
    if meta.is_file():
        try:
            saved=json.loads(meta.read_text(encoding='utf-8'))
            config=saved.get('config') if isinstance(saved,dict) else None
            if isinstance(config,dict):
                old_url=config.get('server_url')
                new_url=migrate_local_url(old_url)
                if old_url!=new_url:
                    config['server_url']=new_url
                    temp=meta.with_suffix('.json.new')
                    temp.write_text(json.dumps(saved,indent=2),encoding='utf-8')
                    temp.replace(meta)
        except (OSError,ValueError):
            pass
    if all((target/n).is_file() and (target/n).read_bytes()==b for n,b in files.items()):
        return 'Anki desktop bridge installed'
    # Individual atomic replacement means Anki never imports a half-written
    # Python source file. Existing meta.json/config persists across updates.
    for name, contents in files.items():
        dest=target/name;stage=target/(name+'.new')
        stage.write_bytes(contents);stage.replace(dest)
    return 'Anki desktop bridge installed; active after Anki next starts'


def bootstrap():
    token=ensure_server()
    client=Client(LOCAL_URL,token)
    skin_message=recover_eren(client)
    bridge_message=ensure_anki_bridge()
    return {'url':LOCAL_URL,'token':token,'allow_lan_http':False,
            'skin_message':skin_message,'bridge_message':bridge_message}



def export_hosted_state(destination):
    """GUI-only, one-time migration export; normal updates never need it."""
    from server.backup import snapshot_server, verify_snapshot, SnapshotError
    path=Path(destination).expanduser()
    if path.suffix.lower()!=".zip" or not path.parent.is_dir():
        raise ValueError("Choose an existing folder and a .zip migration filename")
    if path.exists():
        raise FileExistsError("Migration archive already exists; choose a different filename")
    archive=snapshot_server(data_dir(),path.parent)
    if archive is None:
        raise RuntimeError("Original Windows server history was not found")
    manifest=verify_snapshot(archive)
    if "token.txt" not in manifest["files"]:
        archive.unlink(missing_ok=True)
        raise RuntimeError("Original server token is missing; cannot export a usable migration")
    archive.replace(path)
    path.chmod(0o600)
    return str(path)

def _tunnel_executable():
    base = Path(sys.executable).resolve().parent
    candidates = [base.parent / "tools" / "cloudflared.exe",
                  data_dir() / "cloudflared.exe"]
    for path in candidates:
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == CLOUDFLARED_SHA256:
            return path
    raise RuntimeError("The bundled phone connection component is missing or damaged")


def _existing_pairing(token):
    path = data_dir() / "pairing-link.txt"
    if not path.is_file():
        return None
    link = path.read_text(encoding="utf-8").strip()
    parsed = urlsplit(link)
    url = f"{parsed.scheme}://{parsed.netloc}"
    if PAIRING_HOST.fullmatch(url) and _healthy(url, timeout=3):
        return url + "?" + urlencode({"token": token, "collection_id": "primary"})
    return None


def pair_phone():
    """Provision a free short-lived HTTPS relay when Pair phone is clicked.

    Quick Tunnel hostnames may rotate across restarts. This is pairing, not
    permanent hosted infrastructure.
    """
    token = ensure_server()
    existing = _existing_pairing(token)
    if existing:
        return existing
    program = _tunnel_executable()
    home = data_dir()
    home.mkdir(parents=True, exist_ok=True)
    log_path = home / "pairing-tunnel.log"
    # Cloudflared writes the generated temporary URL to stderr.
    with log_path.open("wb") as log:
        process = hidden_process([str(program), "tunnel", "--no-autoupdate",
                                  "--url", LOCAL_URL],
                                 cwd=str(home), stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 80
    attempted = set()
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Secure phone connection exited before a link was created")
        try:
            output = log_path.read_text(encoding="utf-8", errors="replace")[-12000:]
        except OSError:
            output = ""
        for url in re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", output):
            if PAIRING_HOST.fullmatch(url) and (url not in attempted or time.monotonic() > deadline - 60):
                attempted.add(url)
                if _healthy(url, timeout=3):
                    link = url + "?" + urlencode({"token": token, "collection_id": "primary"})
                    path = home / "pairing-link.txt"
                    path.write_text(link, encoding="utf-8")
                    path.chmod(0o600)
                    return link
        time.sleep(1)
    raise RuntimeError("Could not establish an HTTPS phone connection. Check your Internet connection")
