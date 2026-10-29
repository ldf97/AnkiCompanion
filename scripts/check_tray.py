"""Render actual Qt tray icons and verify progress/docking; not Windows OS proof."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,tempfile
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap,QPainter,QColor
from PySide6.QtCore import Qt
from desktop.app import Window,streak_tray_icon,STYLE
from server.main import create_app
from fastapi.testclient import TestClient
app=QApplication([]);app.setStyleSheet(STYLE);app.setQuitOnLastWindowClosed(False)
sheet=QPixmap(760,410);sheet.fill(QColor('#202329'));paint=QPainter(sheet);paint.setPen(QColor('white'))
for row,(streak,done) in enumerate([(0,False),(72,False),(1234,True)]):
    icon=streak_tray_icon(streak,done)
    paint.drawText(12,30+row*130,f'{streak}, '+('lit' if done else 'hollow'))
    for column,size in enumerate((16,24,32,128)):
        image=icon.pixmap(size,size);image.save(str(root/'test-results'/f'tray-{streak}-{size}.png'))
        paint.drawPixmap(160+column*145,10+row*130,image)
        paint.drawText(160+column*145,120+row*130,f'{size}px')
paint.end();sheet.save(str(root/'test-results/tray-contact-sheet.png'))
with tempfile.TemporaryDirectory() as tmp:
    c=TestClient(create_app(Path(tmp)/'server','tray-test-token-123'),headers={'Authorization':'Bearer tray-test-token-123'})
    s=c.get('/v1/settings').json();c.put('/v1/settings',json=dict(s,lesson_answers=50,lesson_ms=0))
    value=c.get('/v1/state').json();value['progress'].update(answers=30,duration_ms=0);value['streak']=72
    win=Window(Path(tmp)/'desktop',autostart=False);win.show()
    win.receive((value,True,'','test',None,None,False,False));app.processEvents()
    assert win.progress.value()==60 and '20 remaining' in win.count.text() and '60%' in win.count.text()
    win.close();app.processEvents();assert win.dock.isVisible() and not win.isVisible()
    win.restore();app.processEvents();assert win.isVisible() and not win.dock.isVisible()
    value['progress']['answers']=50;value['completed']=True
    win.receive((value,True,'','done',None,None,False,False));app.processEvents()
    assert win.progress.value()==100 and '0 remaining' in win.count.text()
    win.quitting=True;win.close();win.dock.hide();win.tray.hide()
print('PASS: 30/50 => 60%, 20 remaining; 50/50 => 100%, 0 remaining; dock restores')
print('Rendered hollow/lit flame above number at 16, 24, 32 and 128 pixels; inspect tray-contact-sheet.png')
print('VERIFICATION LEVEL: Qt offscreen rendering only, not actual Windows tray or physical-device sync')
