"""Bootstrapping and private-asset recovery are testable without touching Anki."""
import hashlib
import io
import zipfile
from urllib.parse import parse_qs, urlsplit

from desktop import bootstrap as setup


def test_finds_only_verified_original_eren_inside_existing_download(tmp_path, monkeypatch):
    skin=b"this simulates the user's exact original skin zip bytes"
    monkeypatch.setattr(setup, "EREN_SHA256", hashlib.sha256(skin).hexdigest())
    archive=tmp_path/"AnkiCompanion_Updated_Main_Eren_2026-10-31.zip"
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("Windows/Eren-Anki-Private-Skin-1.0.0.zip", skin)
    monkeypatch.setattr(setup, "_private_candidates", lambda: iter([archive]))
    assert setup.find_original_eren()==skin
    monkeypatch.setattr(setup, "EREN_SHA256", "0"*64)
    assert setup.find_original_eren() is None


def test_recovers_eren_without_overwriting_study_history(tmp_path, monkeypatch):
    private=b"original-private-pack"
    monkeypatch.setattr(setup, "find_original_eren",lambda:private)
    settings={"skin_id":"study_companion","skin_version":"1.0.0","revision":11,
              "lesson_answers":50,"lesson_ms":300000}
    calls=[]
    class Client:
        def request(self, path, method="GET", data=None, **kwargs):
            calls.append((path,method,data))
            if path=="/v1/skins":return {"skins":[{"id":"study_companion","version":"1.0.0"}]}
            if path=="/v1/skins/import":
                assert data==private
                return {"id":"eren_anki","version":"1.0.0"}
            if path=="/v1/settings":
                if method=="GET":return dict(settings)
                assert data["lesson_answers"]==50 and data["lesson_ms"]==300000
                assert data["revision"]==11
                return data
            raise AssertionError(path)
    assert setup.recover_eren(Client())=="Eren artwork activated"
    assert [x[0] for x in calls]==["/v1/skins","/v1/skins/import","/v1/settings","/v1/settings"]


def test_previously_imported_eren_needs_no_private_file(monkeypatch):
    class Client:
        def request(self,path,method="GET",data=None,**kwargs):
            if path=="/v1/skins":return {"skins":[{"id":"eren_anki","version":"1.0.0"}]}
            if path=="/v1/settings":return {"skin_id":"eren_anki","skin_version":"1.0.0"}
            raise AssertionError("Unexpected alteration")
    monkeypatch.setattr(setup,"find_original_eren",lambda: (_ for _ in ()).throw(AssertionError("Should not need ZIP")))
    assert setup.recover_eren(Client())=="Eren artwork available; selected skin preserved"


def test_pairing_uses_existing_live_relay_without_spawning_a_new_process(tmp_path,monkeypatch):
    monkeypatch.setattr(setup,"data_dir",lambda:tmp_path)
    (tmp_path/"pairing-link.txt").write_text("https://active-bridge.trycloudflare.com?token=old&collection_id=primary")
    monkeypatch.setattr(setup,"ensure_server",lambda:"private_token_abcdefghijkl")
    monkeypatch.setattr(setup,"_healthy",lambda url,timeout=1.5:url=="https://active-bridge.trycloudflare.com")
    monkeypatch.setattr(setup,"_tunnel_executable",lambda: (_ for _ in ()).throw(AssertionError("Unexpected process spawn")))
    url=setup.pair_phone()
    assert urlsplit(url).hostname=="active-bridge.trycloudflare.com"
    assert parse_qs(urlsplit(url).query)=={"token":["private_token_abcdefghijkl"],"collection_id":["primary"]}


def test_private_pairing_never_returns_http_or_unauthorized_url(tmp_path,monkeypatch):
    monkeypatch.setattr(setup,"data_dir",lambda:tmp_path)
    (tmp_path/"pairing-link.txt").write_text("http://127.0.0.1:8765?token=secret")
    assert setup._existing_pairing("new-token") is None
    (tmp_path/"pairing-link.txt").write_text("https://not-cloudflare.example?token=secret")
    assert setup._existing_pairing("new-token") is None


def test_relaunch_does_not_override_existing_custom_skin():
    class Client:
        def request(self, path, method="GET", data=None, **kwargs):
            if path == "/v1/skins":
                return {"skins": [{"id": "eren_anki", "version": "1.0.0"},
                                  {"id": "new_custom", "version": "2.0.0"}]}
            raise AssertionError("Bootstrap must not rewrite custom skin selection")
    assert "selected skin preserved" in setup.recover_eren(Client())


def test_first_eren_import_preserves_already_selected_custom_skin(monkeypatch):
    monkeypatch.setattr(setup, "find_original_eren", lambda: b"original-pack")
    selected = {"skin_id": "new_custom", "skin_version": "2.0.0", "lesson_answers": 71}
    writes = []
    class Client:
        def request(self, path, method="GET", data=None, **kwargs):
            if path == "/v1/skins":
                return {"skins": [{"id": "new_custom", "version": "2.0.0"}]}
            if path == "/v1/skins/import":
                assert data == b"original-pack"
                return {"id": "eren_anki", "version": "1.0.0"}
            if path == "/v1/settings" and method == "GET":
                return dict(selected)
            if path == "/v1/settings" and method == "PUT":
                writes.append(data)
                return data
            raise AssertionError(path)
    assert "selected skin preserved" in setup.recover_eren(Client())
    assert writes == []
    assert selected["skin_id"] == "new_custom"

def test_hosted_connection_survives_windows_startup_without_local_bootstrap():
    from urllib.parse import urlsplit, parse_qs
    remote={"url":"https://companion.example.net","token":"secret-12345678901234567890",
            "allow_lan_http":False}
    assert setup.has_remote_connection(remote)
    link=setup.remote_pairing_link(remote)
    assert urlsplit(link).hostname=="companion.example.net"
    assert parse_qs(urlsplit(link).query)["token"]==[remote["token"]]
    assert not setup.has_remote_connection(dict(remote,url="http://companion.example.net"))
    assert not setup.has_remote_connection(dict(remote,url="http://127.0.0.1:8765"))
    assert not setup.has_remote_connection(dict(remote,url="https://companion.example.net?override=1"))
    assert not setup.has_remote_connection(dict(remote,token=""))
    # GUI bootstrap must consult this guard BEFORE starting the local server.
    source=(__import__("pathlib").Path(__file__).resolve().parents[1]/"desktop/app.py").read_text()
    method=source.split("    def bootstrap_local(self):",1)[1].split("    def client(self):",1)[0]
    assert "if first_run.has_remote_connection(self.config):" in method
    assert method.index("if first_run.has_remote_connection(self.config):") < method.index("first_run.bootstrap")
    assert "Using saved always-on companion server" in method
    assert "remote_pairing_link(self.config)" in source


def test_pairing_requires_https_and_preserves_existing_hosted_endpoint():
    config={"url":"https://my-host.example.org","token":"0123456789abcdef","allow_lan_http":False}
    assert setup.remote_pairing_link(config).startswith("https://my-host.example.org?token=")
    config["url"]="http://192.168.1.3:8765"
    config["allow_lan_http"]=True
    assert setup.has_remote_connection(config)
    import pytest
    with pytest.raises(ValueError,match="HTTPS"):
        setup.remote_pairing_link(config)

def test_gui_export_creates_verified_original_server_snapshot_without_mutation(tmp_path,monkeypatch):
    from pathlib import Path
    from server.main import create_app
    from server.backup import verify_snapshot
    from zipfile import ZipFile
    import pytest
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"Local"))
    source=setup.data_dir()
    create_app(source)
    original_db=(source/"companion.sqlite3").read_bytes()
    original_token=(source/"token.txt").read_bytes()
    dest=tmp_path/"AnkiCompanion-Server-Migration.zip"
    path=setup.export_hosted_state(dest)
    assert Path(path)==dest
    manifest=verify_snapshot(dest)
    assert "companion.sqlite3" in manifest["files"]
    with ZipFile(dest) as archive:
        assert archive.read("token.txt")==original_token
    assert (source/"companion.sqlite3").read_bytes()==original_db
    assert (source/"token.txt").read_bytes()==original_token
    with pytest.raises(FileExistsError):
        setup.export_hosted_state(dest)
