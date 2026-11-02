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
