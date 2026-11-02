"""Google Cloud provision/persistence safety tests, without account access."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_gce_has_two_protected_disks_and_native_sqlite():
    tf=(ROOT/"deployment/google-cloud/main.tf").read_text()
    assert 'machine_type = "e2-micro"' in tf
    assert 'backend "gcs"' in tf
    assert tf.count("prevent_destroy = true")==2
    assert 'size = 10' in tf and 'size = 15' in tf and 'size = 5' in tf
    assert 'device_name = "ankicompanion-data"' in tf
    assert 'device_name = "ankicompanion-backups"' in tf
    assert 'snapshot_schedule_policy' in tf
    assert 'source_ranges = ["35.235.240.0/20"]' in tf
    assert 'source_ranges = ["0.0.0.0/0"]' in tf

def test_gce_startup_refuses_blank_migration_and_formats_only_unformatted_disks():
    s=(ROOT/"deployment/google-cloud/startup.sh.tftpl").read_text()
    assert 'MIGRATION_REQUIRED' in s
    assert 'mount_existing_or_blank_disk ankicompanion-data' in s
    assert 'mount_existing_or_blank_disk ankicompanion-backups' in s
    assert 'if ! blkid' in s and "mkfs.ext4" in s
    assert 'docker volume inspect' in s
    assert 'git fetch --depth 1 origin' in s
    assert 'git rev-parse HEAD' in s
    assert 'docker compose --env-file' in s

def test_gce_web_deployment_requires_owner_authorization():
    w=(ROOT/".github/workflows/deploy-google-cloud.yml").read_text()
    assert "github.ref == 'refs/heads/main'" in w
    assert "environment: google-cloud-production" in w
    assert "google-github-actions/auth@v2" in w
    assert 'workload_identity_provider:' in w
    assert "GCP_TF_STATE_BUCKET" in w
    assert "if: inputs.apply" in w
    assert "terraform plan" in w and "terraform apply" in w
