"""Verify the actual Qt Update button, not merely the update helper functions.

GitHub's separate Windows CI performs the real installer/restart and data-preservation checks.
This test proves the button can reach that verified installer without any server pairing.
"""
import os
from pathlib import Path
from unittest.mock import Mock
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_unpaired_desktop_update_button_initiates_verified_install(monkeypatch, tmp_path):
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    from desktop.app import Window
    from companion import updates

    qt = QApplication.instance() or QApplication([])
    window = Window(storage=tmp_path / "unpaired-profile", autostart=False)
    window.show()
    qt.processEvents()
    assert not window.config.get("token"), "fixture must be genuinely unpaired"

    target = tmp_path / "AnkiCompanion-Windows-Setup.exe"
    target.write_bytes(b"small-fixture-only-not-an-executable")
    release = {
        "configured": True, "available": True, "version": "0.1.2",
        "commit": "update-button-acceptance-test",
        "filename": target.name, "sha256": "a" * 64, "size": target.stat().st_size,
        "download_url": updates.PUBLIC_RELEASES + target.name,
        "components": {"windows_desktop": {"asset": "windows"}},
    }
    calls = []

    def github_release(platform):
        calls.append(("looked_up", platform))
        return release

    def downloaded(offer, folder):
        # Official GitHub updates do not require an API server or pairing token.
        assert offer == release
        calls.append(("downloaded", target.name))
        return target

    def installed(path, offer):
        assert path == target and offer == release
        calls.append(("installer_launched", path.name))

    monkeypatch.setattr(updates, "github_release", github_release)
    monkeypatch.setattr(updates, "download", downloaded)
    monkeypatch.setattr(updates, "install", installed)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kw: QMessageBox.StandardButton.Yes)
    # Replace thread scheduling, not the GUI button's signal/action chain.
    window.launch = lambda work, after, **kwargs: after(work())
    window.quit_app = lambda: calls.append(("desktop_restarts", True))

    try:
        QTest.mouseClick(window.update_button, Qt.MouseButton.LeftButton)
        assert [x[0] for x in calls] == [
            "looked_up", "downloaded", "installer_launched", "desktop_restarts"
        ], calls
        assert window.update_button.text().startswith("Update Windows bundle to 0.1.2")
        assert release["download_url"].startswith(updates.PUBLIC_RELEASES)
        assert not window.config.get("token")
    finally:
        window.quitting = True
        window.close()
        window.dock.hide()
        window.tray.hide()


def test_failed_unpaired_update_check_shows_persistent_error(monkeypatch, tmp_path):
    """The GitHub failure must remain visible despite unrelated server errors."""
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    from desktop.app import Window

    qt = QApplication.instance() or QApplication([])
    window = Window(storage=tmp_path / "no-server", autostart=False)
    window.show()
    qt.processEvents()
    assert not window.config.get("token")
    notices = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: notices.append(args)
    )

    def failing_check(work, after, **kwargs):
        assert "error" in kwargs
        kwargs["error"]("Connection refused by update host")
        return None

    window.launch = failing_check
    try:
        QTest.mouseClick(window.update_button, Qt.MouseButton.LeftButton)
        assert window._update_check_busy is False
        assert "Update check failed" in window.update_status.text()
        assert "Connection refused" in window.update_status.text()
        assert notices, "Manual update errors must not be silently lost"
        # This status is independent of the study server's refreshed label.
        window.status.setText("Offline: local server unavailable")
        assert "Connection refused" in window.update_status.text()
    finally:
        window.quitting = True
        window.close()
        window.dock.hide()
        window.tray.hide()
