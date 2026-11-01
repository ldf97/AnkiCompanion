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
    assert setup.recover_eren(Client())=="Eren artwork activated"


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


def test_automatically_installs_and_updates_addon_without_losing_metadata(tmp_path, monkeypatch):
    from desktop import bootstrap as setup
    from zipfile import ZipFile
    import json
    appdata = tmp_path / "Roaming"
    base = appdata / "Anki2" / "addons21"
    base.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    archive = tmp_path / "Anki_Companion_Bridge.ankiaddon"
    payload = {"__init__.py": b"# version 1", "history.py": b"pass",
               "rules.py": b"pass", "transport.py": b"pass",
               "manifest.json": b'{"package":"anki_companion_bridge"}',
               "config.json": b'{"auto_sync":true}', "config.md": b"Safe addon"}
    def package():
        with ZipFile(archive,"w") as z:
            for name, data in payload.items():
                z.writestr(name, data)
    package()
    monkeypatch.setattr(setup,"addon_archive",lambda:archive)
    assert "installed" in setup.ensure_anki_bridge()
    folder=base/"anki_companion_bridge"
    assert (folder/"__init__.py").read_bytes()==b"# version 1"
    (folder/"meta.json").write_text('{"config":{"user_choice":"keep"}}')
    payload["__init__.py"]=b"# version 2"
    package()
    assert "installed" in setup.ensure_anki_bridge()
    assert (folder/"__init__.py").read_bytes()==b"# version 2"
    assert json.loads((folder/"meta.json").read_text())["config"]["user_choice"]=="keep"
    assert setup.ensure_anki_bridge()=="Anki desktop bridge installed"


def test_addon_package_rejects_extra_paths(tmp_path,monkeypatch):
    from desktop import bootstrap as setup
    from zipfile import ZipFile
    appdata = tmp_path/"Roaming"
    (appdata/"Anki2").mkdir(parents=True)
    monkeypatch.setenv("APPDATA",str(appdata))
    archive=tmp_path/"malicious.ankiaddon"
    with ZipFile(archive,"w") as z:
        z.writestr("../bad",b"bad")
    monkeypatch.setattr(setup,"addon_archive",lambda:archive)
    import pytest
    with pytest.raises(RuntimeError,match="validation"):
        setup.ensure_anki_bridge()
    assert not (tmp_path/"bad").exists()
