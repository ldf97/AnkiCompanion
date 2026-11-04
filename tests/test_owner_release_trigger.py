"""Only the owner can cause the release workflow to consume signing secrets.

GitHub issue comments are used solely as a transport for two hard-coded
commands: no untrusted comment is interpolated into any executable shell.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_owner_only_release_request_is_scoped_to_control_issue():
    workflow = (ROOT / ".github/workflows/owner-release-trigger.yml").read_text()
    assert "issue_comment:" in workflow
    assert "types: [created]" in workflow
    assert "github.repository == 'ldf97/AnkiCompanion'" in workflow
    assert "github.event.issue.number == 23" in workflow
    assert "!github.event.issue.pull_request" in workflow
    assert "github.event.comment.user.login == github.repository_owner" in workflow
    assert "github.event.comment.body == '/prepare-release v0.1.2 build=3'" in workflow
    assert "github.event.comment.body == '/publish-release v0.1.2 build=3'" in workflow
    assert "secrets: inherit" in workflow


def test_no_credentials_exposed_and_publishing_requires_second_command():
    workflow = (ROOT / ".github/workflows/owner-release-trigger.yml").read_text()
    assert "environment: signing" in workflow
    assert "secrets.ANDROID_SIGNING_BUNDLE" in workflow
    assert "secrets.ANDROID_KEYSTORE_BASE64" in workflow
    assert "Missing persistent Android signing key" in workflow
    assert "publish: false" in workflow
    assert "publish: true" in workflow
    assert "uses: ./.github/workflows/release-candidate.yml" in workflow
    assert "gh release create" not in workflow
    assert "eval(" not in workflow
    assert "github.event.comment.body }}" not in workflow
