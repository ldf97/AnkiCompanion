"""One-time cloud migration is lossless and fails closed without user scripts."""
import json
import sqlite3
from pathlib import Path
from zipfile import ZipFile
import pytest
from fastapi.testclient import TestClient
from server.main import create_app
from server.backup import snapshot_server, SnapshotError
from scripts.restore_hosted import restore_hosted


def test_google_vm_migrates_original_review_history_settings_token_and_private_artwork(tmp_path):
    old=tmp_path/"windows";app=create_app(old)
    token=(old/"token.txt").read_text()
    with TestClient(app,headers={"Authorization":"Bearer "+token}) as client:
        settings=client.get("/v1/settings").json()
        settings["lesson_answers"]=47
        assert client.put("/v1/settings",json=settings).status_code==200
        now=__import__("time").time_ns()//1000000
        assert client.post("/v1/events",json={"events":[{
            "collection_id":"primary","revlog_id":now-60000,
            "card_id":42,"duration_ms":3000,"rating":4
        }]}).status_code==200
        original=client.get("/v1/state").json()
    art=old/"packs"/"eren_anki"/"1.0.0"/"frames"
    art.mkdir(parents=True)
    (art/"private.png").write_bytes(b"EXACT PRIVATE ORIGINAL FIXTURE")
    archive=snapshot_server(old,tmp_path/"exports")
    cloud=tmp_path/"google_vm"
    manifest=restore_hosted(archive,cloud)
    assert manifest["schema"]==1
    assert (cloud/"token.txt").read_text()==token
    assert (cloud/"packs"/"eren_anki"/"1.0.0"/"frames"/"private.png").read_bytes()==b"EXACT PRIVATE ORIGINAL FIXTURE"
    with TestClient(create_app(cloud),headers={"Authorization":"Bearer "+token}) as client:
        restored=client.get("/v1/state").json()
        assert restored["settings"]==original["settings"]
        assert restored["progress"]==original["progress"]
        assert restored["seed"]==original["seed"]
    with pytest.raises(SnapshotError,match="already"):
        restore_hosted(archive,cloud)


def test_cloud_migration_rejects_corrupt_and_partial_files_without_reset(tmp_path):
    old=tmp_path/"old"
    create_app(old)
    archive=snapshot_server(old,tmp_path/"exports")
    corrupt=tmp_path/"damaged.zip"
    corrupt.write_bytes(archive.read_bytes()[:-50])
    cloud=tmp_path/"cloud"
    with pytest.raises(Exception):
        restore_hosted(corrupt,cloud)
    assert not (cloud/"companion.sqlite3").exists()
    assert not (cloud/"token.txt").exists()


def test_google_startup_can_import_from_browser_uploaded_archive():
    source=(Path(__file__).resolve().parents[1]/"deployment/google-cloud/startup.sh.tftpl").read_text()
    assert 'AnkiCompanion-Server-Migration.zip' in source
    assert "python3 -m scripts.restore_hosted" in source
    assert source.index("scripts.restore_hosted") < source.index("MIGRATION_REQUIRED")
