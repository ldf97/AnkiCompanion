"""Headless desktop integration check. Actual Windows tray remains a device check."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys, tempfile, json, time
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from PySide6.QtWidgets import QApplication
from desktop.app import Window, STYLE
from server.main import create_app
from fastapi.testclient import TestClient
from app.widget_engine import WidgetEngine
import io

app=QApplication([]);app.setStyleSheet(STYLE);app.setQuitOnLastWindowClosed(False)
with tempfile.TemporaryDirectory() as temp:
    server=create_app(Path(temp)/'server','desktop-test-token-123')
    api=TestClient(server,headers={'Authorization':'Bearer desktop-test-token-123'})
    value=api.get('/v1/state').json()
    engine=WidgetEngine(root/'skins/eren_anki',Path(temp)/'frames')
    frame=engine.render(value['scene'],include_warning=False).read_bytes()
    warning=io.BytesIO();engine.icon('warning_badge',58,58).save(warning,format='PNG')
    win=Window(Path(temp)/'desktop',autostart=False);win.show();app.processEvents()
    win.receive((value,True,'','test',frame,warning.getvalue(),True,False));app.processEvents()
    assert win.isVisible()
    win.close();app.processEvents()
    assert not win.isVisible() and win.dock.isVisible(), 'X must collapse to dock'
    win.restore();app.processEvents()
    assert win.isVisible() and not win.dock.isVisible(), 'Dock must restore main window'
    destination=root/'test-results/desktop-ui.png';win.grab().save(str(destination))
    assert destination.stat().st_size>10000
    print('PASS: authenticated server state rendered in native desktop UI')
    print('PASS: X collapses to compact dock; Open restores main window')
    print('Saved screenshot:',destination)
    win.quitting=True;win.close();win.dock.hide();win.tray.hide()
print('Remaining: native window/tray behavior on Windows/macOS; physical device testing')
