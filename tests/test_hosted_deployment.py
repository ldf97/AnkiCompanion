"""Static deployment invariants; real DNS/cloud credentials are not available in CI."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_hosted_compose_is_persistent_tls_and_restarts():
    compose=(ROOT/'deployment/compose.yaml').read_text()
    assert 'ankicompanion_data:' in compose and 'external: true' in compose
    assert compose.count('restart: unless-stopped')==2
    assert 'ankicompanion_data:/data:rw' in compose
    assert "'443:443'" in compose
    assert 'condition: service_healthy' in compose
    dockerfile=(ROOT/'server/Dockerfile').read_text()
    assert 'ANKI_COMPANION_DATA=/data' in dockerfile


def test_deployment_never_disables_ssh_host_validation_or_overwrites_credentials():
    flow=(ROOT/'.github/workflows/deploy-hosted.yml').read_text()
    assert 'StrictHostKeyChecking=yes' in flow
    assert 'DEPLOY_KNOWN_HOSTS' in flow
    assert 'docker volume inspect ankicompanion_data' in flow
    assert 'git archive --format=tar HEAD' in flow
    assert 'check_hosted.py' in flow
    assert 'docker compose --env-file .env' in flow
    assert not any(word in flow for word in ('StrictHostKeyChecking=no','docker compose down -v','docker volume rm'))


def test_public_ingress_tls_auth_check():
    caddy=(ROOT/'deployment/Caddyfile').read_text()
    assert 'reverse_proxy api:8765' in caddy
    assert '{$COMPANION_DOMAIN}' in caddy
    src=(ROOT/'scripts/check_hosted.py').read_text()
    assert '/v1/state' in src and '401' in src

def test_live_wal_snapshot_preserves_history_token_and_private_skin(tmp_path):
    import json
    import sqlite3
    from zipfile import ZipFile
    from server.main import create_app
    from server.backup import snapshot_server, verify_snapshot
    from fastapi.testclient import TestClient

    home=tmp_path/"live"
    app=create_app(home,clock=lambda:1783094400000)
    token=(home/"token.txt").read_text()
    with TestClient(app,headers={"Authorization":"Bearer "+token}) as client:
        settings=client.get("/v1/settings").json()
        assert client.put("/v1/settings",json=dict(settings,lesson_answers=71)).status_code==200
        review=dict(collection_id="primary",revlog_id=1783094300000,card_id=971,
                    duration_ms=1200,rating=4)
        assert client.post("/v1/events",json={"events":[review]}).status_code==200
    skin=home/"packs"/"private_custom"/"1.0.0";skin.mkdir(parents=True)
    (skin/"art.png").write_bytes(b"PRIVATE TEST BYTES")
    saved=snapshot_server(home,tmp_path/"backups")
    manifest=verify_snapshot(saved)
    assert set(manifest["files"])=={"companion.sqlite3","token.txt",
                                    "packs/private_custom/1.0.0/art.png"}
    with ZipFile(saved) as archive:
        assert archive.read("token.txt").decode()==token
        assert archive.read("packs/private_custom/1.0.0/art.png")==b"PRIVATE TEST BYTES"
        restored=tmp_path/"snapshot.sqlite3"
        restored.write_bytes(archive.read("companion.sqlite3"))
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==1
        saved_settings=json.loads(db.execute("SELECT value FROM meta WHERE key='settings'").fetchone()[0])
        assert saved_settings["lesson_answers"]==71


def test_snapshot_skips_virgin_install_and_detects_corruption(tmp_path):
    import pytest
    from server.backup import snapshot_server, verify_snapshot, SnapshotError
    assert snapshot_server(tmp_path/"new",tmp_path/"backup") is None
    from server.main import create_app
    home=tmp_path/"live"
    create_app(home)
    saved=snapshot_server(home,tmp_path/"backup")
    assert saved is not None and verify_snapshot(saved)["schema"]==1
    # Invalid/truncated ZIP must never pass as a verified backup.
    saved.write_bytes(saved.read_bytes()[:100])
    with pytest.raises((SnapshotError,Exception)):
        verify_snapshot(saved)


def test_deployment_backs_up_before_replacing_running_container():
    script=(ROOT/'.github/workflows/deploy-hosted.yml').read_text()
    assert script.index("server.backup snapshot") < script.index("up -d --wait --remove-orphans")
    assert "docker volume inspect ankicompanion_backups" in script
    compose=(ROOT/'deployment/compose.yaml').read_text()
    assert "ankicompanion_backups:/backups:rw" in compose
    assert "name: ankicompanion_backups" in compose

def test_container_startup_captures_existing_state_before_any_schema_migration(tmp_path,monkeypatch):
    from server.main import create_app
    from server.launch import prepare_hosted_start
    from server.backup import verify_snapshot
    data=tmp_path/"data";backups=tmp_path/"backups"
    create_app(data)
    monkeypatch.setenv("ANKI_COMPANION_DATA",str(data))
    monkeypatch.setenv("ANKI_COMPANION_BACKUPS",str(backups))
    assert prepare_hosted_start() is not None
    files=list(backups.glob("server-*.zip"))
    assert len(files)>=1 and "companion.sqlite3" in verify_snapshot(files[0])["files"]
    monkeypatch.setenv("ANKI_COMPANION_BACKUPS",str(tmp_path/"missing"))
    import pytest
    with pytest.raises(RuntimeError,match="backups volume"):
        prepare_hosted_start()


def test_railway_definition_has_two_persistent_volumes_and_one_replica():
    source=(ROOT/".railway/railway.ts").read_text()
    assert 'volume("ankicompanion-data"' in source
    assert 'volume("ankicompanion-backups"' in source
    assert '"/data": data' in source and '"/backups": backups' in source
    assert 'replicas: 1' in source
    assert 'source: github("ldf97/AnkiCompanion"' in source
    assert 'RAILWAY_DOCKERFILE_PATH: "server/Dockerfile"' in source
    assert "server.launch" in source
    docker=(ROOT/"server/Dockerfile").read_text()
    assert 'server.launch' in docker
