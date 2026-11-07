"""Windows Qt Update button delegates to the packaged Electron/NSIS updater.

The Python GUI must never make update HTTP requests or depend on a study token.
The Electron updater tests verify the actual library-based download/install.
"""
import os
from pathlib import Path
import pytest

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

def make_window(tmp_path):
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication
    from desktop.app import Window
    app=QApplication.instance() or QApplication([])
    win=Window(storage=tmp_path/"unpaired-profile",autostart=False)
    win.show()
    app.processEvents()
    assert not win.config.get("token")
    return win

def close_window(window):
    window.quitting=True
    window.close()
    window.dock.hide()
    window.tray.hide()

def test_unpaired_update_button_opens_electron_without_server(monkeypatch,tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from desktop import app as desktop_app
    window=make_window(tmp_path)
    root=tmp_path/"program"
    child=root/"resources"/"desktop"/"AnkiCompanion.exe"
    child.parent.mkdir(parents=True)
    child.write_bytes(b"fixture, not executable")
    shell=root/"AnkiCompanion.exe"
    shell.write_bytes(b"fixture, not executable")
    calls=[]
    scheduled=[]
    nonce="a"*32
    from types import SimpleNamespace
    monkeypatch.setattr(desktop_app.sys,"frozen",True,raising=False)
    monkeypatch.setattr(desktop_app.sys,"executable",str(child))
    monkeypatch.setattr(desktop_app.subprocess,"Popen",
                        lambda argv,**kwargs:calls.append(list(argv)))
    monkeypatch.setattr(desktop_app.uuid,"uuid4",lambda:SimpleNamespace(hex=nonce))
    monkeypatch.setattr(desktop_app.tempfile,"gettempdir",lambda:str(tmp_path))
    monkeypatch.setattr(desktop_app,"QTimer",SimpleNamespace(
        singleShot=lambda delay,callback:scheduled.append(callback)))
    window.quit_app=lambda:calls.append("gui_quit")
    try:
        QTest.mouseClick(window.update_button,Qt.MouseButton.LeftButton)
        assert calls==[[str(shell),"--updates",f"--updates-request={nonce}"]],calls
        assert "Opening Windows updater" in window.update_status.text()
        assert not window.update_button.isEnabled()
        assert scheduled
        assert "gui_quit" not in calls  # No premature shutdown.
        marker=tmp_path/f"ankicompanion-updates-{nonce}.ready"
        marker.write_text("ready",encoding="utf-8")
        scheduled.pop(0)()
        assert calls[-1]=="gui_quit"
        assert not marker.exists()
        assert not window.config.get("token")
    finally: close_window(window)

def test_missing_electron_shell_reports_error_without_quitting(monkeypatch,tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMessageBox
    from desktop import app as desktop_app
    window=make_window(tmp_path)
    child=tmp_path/"old-inno"/"desktop"/"AnkiCompanion.exe"
    child.parent.mkdir(parents=True)
    child.write_bytes(b"fixture")
    warnings=[]
    monkeypatch.setattr(desktop_app.sys,"frozen",True,raising=False)
    monkeypatch.setattr(desktop_app.sys,"executable",str(child))
    monkeypatch.setattr(QMessageBox,"warning",lambda *args,**kwargs:warnings.append(args))
    window.quit_app=lambda:pytest.fail("Do not quit if updater is missing")
    try:
        QTest.mouseClick(window.update_button,Qt.MouseButton.LeftButton)
        assert warnings
        assert "missing" in window.update_status.text().lower()
    finally:close_window(window)
