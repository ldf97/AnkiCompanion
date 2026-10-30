"""Exercise the production desktop timer and rendering while AnkiDroid reviews."""
from pathlib import Path
import sys,os,json,time,urllib.request
os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['ANKI_COMPANION_SKIN']='study_companion'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from desktop.app import Window,STYLE
root=ROOT/'test-results/cross-device';data=root/'desktop-widget';data.mkdir(exist_ok=True)
(data/'connection.json').write_text(json.dumps(dict(url='http://127.0.0.1:8766',token='emulator-fixture-token')))
app=QApplication([]);app.setStyleSheet(STYLE);app.setQuitOnLastWindowClosed(False)
win=Window(data);win.show();seen=set();deadline=time.monotonic()+600
def inspect():
    if time.monotonic()>deadline:raise RuntimeError('Desktop observer timed out')
    if not win.current:return
    count=win.current['progress']['answers']
    if count not in (30,50) or count in seen:return
    assert win.progress.value()==count*2
    assert f'{50-count} remaining' in win.count.text()
    assert win.dock.progress.value()==count*2
    assert f'{count}/50' in win.dock.count.text()
    assert f'{50-count} remaining' in win.dock.count.text()
    assert win.current['completed']==(count==50)
    win.grab().save(str(root/f'desktop-{count}.png'))
    win.close();assert win.dock.isVisible();win.dock.grab().save(str(root/f'dock-{count}.png'));win.restore()
    req=urllib.request.Request(f'http://127.0.0.1:8766/test/desktop{count}',data=b'{}',headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req) as r:r.read()
    seen.add(count)
    (root/'desktop-widget-observed.json').write_text(json.dumps(sorted(seen)))
timer=QTimer();timer.timeout.connect(inspect);timer.start(200)
app.exec()
