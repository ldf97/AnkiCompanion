"""Owner-controlled release trigger is limited to a GitHub issue comment.

Untrusted text is passed in environment variables and restricted to an exact
numeric release command. It is never interpolated directly into shell script.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_request_is_restricted_to_owner_and_control_issue():
    w = (ROOT / ".github/workflows/owner-release-trigger.yml").read_text()
    assert "issue_comment:" in w and "types: [created]" in w
    assert "github.repository == 'ldf97/AnkiCompanion'" in w
    assert "github.event.issue.number == 23" in w
    assert "!github.event.issue.pull_request" in w
    assert "github.event.comment.user.login == github.repository_owner" in w
    assert "startsWith(github.event.comment.body, '/prepare-release ')" in w
    assert "startsWith(github.event.comment.body, '/publish-release ')" in w


def test_commands_are_validated_not_interpreted_and_dispatch_is_explicit():
    w = (ROOT / ".github/workflows/owner-release-trigger.yml").read_text()
    assert "actions: write" in w
    assert "GH_TOKEN: ${{ github.token }}" in w
    assert "RELEASE_REQUEST: ${{ github.event.comment.body }}" in w
    assert "re.fullmatch(" in w
    assert "build=(\\d+)" in w
    assert "gh workflow run release-candidate.yml --ref main" in w
    assert '--raw-field "publish=$PUBLISH"' in w
    assert "secrets.ANDROID" not in w
    assert "gh release create" not in w
    assert "eval(" not in w
    assert "github.event.comment.body }}" not in w.split("run: |",1)[1]
