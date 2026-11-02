"""Self-contained Windows setup. Run by the app, not by the user.

The public release never contains private Eren artwork or pairing credentials.
Only recover the original verified Eren ZIP from files already on this PC.
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

EREN_SHA256 = "7c25d1434b9971ea89193be60a665b18c0a5ed9be66fa4f92c36c94752dce412"
CLOUDFLARED_SHA256 = "547057326266f0e1c7d50d102dbd22ff283d740c055bd61e94f10e2c606f89af"
PAIRING_HOST = re.compile(r"^https://[a-z0-9-]+\.trycloudflare\.com$")
LOCAL_URL = "http://127.0.0.1:8765"


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


def ensure_server():
    """Start packaged server when it is missing, keeping the same token/data."""
    home = data_dir()
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
    """Look only in common owner download locations, never crawl the whole disk."""
    home = Path.home()
    directories = [home / "Downloads", home / "Desktop", home / "Documents",
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
    """Import/activate the exact owner's original pack, if already on their PC."""
    installed = client.request("/v1/skins")
    exists = any(s["id"] == "eren_anki" and s["version"] == "1.0.0"
                 for s in installed.get("skins", []))
    if not exists:
        data = find_original_eren()
        if data is None:
            return "Original Eren ZIP was not found among files already on this PC"
        imported = client.request("/v1/skins/import", "POST", data,
                                  content_type="application/zip")
        if imported.get("id") != "eren_anki":
            raise RuntimeError("The original Eren skin was rejected by the server")
    settings = client.request("/v1/settings")
    if (settings["skin_id"], settings["skin_version"]) != ("eren_anki", "1.0.0"):
        settings.update(skin_id="eren_anki", skin_version="1.0.0")
        client.request("/v1/settings", "PUT", settings)
    return "Eren artwork activated"


def addon_archive():
    if getattr(sys,'frozen',False):
        return Path(sys.executable).resolve().parent.parent/'Anki_Companion_Bridge.ankiaddon'
    return Path(__file__).resolve().parents[1]/'packages'/'Anki_Companion_Bridge.ankiaddon'


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
        allowed={'__init__.py','bridge.py','history.py','rules.py','transport.py',
                 'config.json','config.md','manifest.json'}
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
    if all((target/n).is_file() and (target/n).read_bytes()==b for n,b in files.items()):
        return 'Anki desktop bridge installed'
    target.mkdir(exist_ok=True)
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
