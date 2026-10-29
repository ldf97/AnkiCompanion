import sys, os, json, time, tempfile, math, threading
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QStandardPaths, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QImage, QAction
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QLabel,QPushButton,QLineEdit,QCheckBox,QComboBox,QSpinBox,QFormLayout,QDialog,
    QDialogButtonBox,QSystemTrayIcon,QMenu,QMessageBox,QFileDialog,QProgressBar)
from companion.transport import Client
from companion.packs import Packs
from companion.rules import scene, daily_lineup, study_day, lesson_progress
from app.widget_engine import WidgetEngine
from companion import updates

ROOT=Path(__file__).resolve().parents[1]

def write_json(path,value,private=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2),encoding='utf-8')
    if private: temp.chmod(0o600)
    temp.replace(path)

class Job(QThread):
    succeeded=Signal(object);failed=Signal(str)
    def __init__(self,func,parent=None):super().__init__(parent);self.func=func
    def run(self):
        try:self.succeeded.emit(self.func())
        except Exception as exc:self.failed.emit(str(exc))

class Panel(QWidget):
    def __init__(self):
        super().__init__();self.pix=QPixmap();self.warning=QPixmap();self.warn=False
        self.setMinimumSize(330,140);self.tick=QTimer(self);self.tick.timeout.connect(self.update);self.tick.start(60)
    def sizeHint(self):return QSize(770,328)
    def set_frame(self,frame,warning,warn):
        self.pix.loadFromData(frame);self.warning.loadFromData(warning);self.warn=warn;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(),QColor('#17191d'))
        if self.pix.isNull():
            p.setPen(QColor('#e7ded1'));p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Connect to your companion server');return
        scale=min(self.width()/1100,self.height()/468);w=1100*scale;h=468*scale
        x=(self.width()-w)/2;y=(self.height()-h)/2
        p.drawPixmap(int(x),int(y),int(w),int(h),self.pix)
        if self.warn and not self.warning.isNull():
            pulse=1+.125*(1-math.cos(time.monotonic()*2*math.pi/1.8));side=58*scale*pulse
            p.drawPixmap(int(x+(95+29)*scale-side/2),int(y+(35+29)*scale-side/2),int(side),int(side),self.warning)

class Dock(QWidget):
    def __init__(self,main):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.main=main;self.origin=None;self.setWindowTitle('Anki Companion dock')
        self.panel=Panel();self.panel.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        box=QVBoxLayout(self);box.setContentsMargins(4,4,4,4);box.addWidget(self.panel)
        row=QHBoxLayout();study=QPushButton('Study');restore=QPushButton('Open');quit_button=QPushButton('Quit')
        study.clicked.connect(main.study);restore.clicked.connect(main.restore);quit_button.clicked.connect(main.quit_app)
        for b in (study,restore,quit_button):row.addWidget(b)
        box.addLayout(row);self.resize(390,210)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.origin=event.globalPosition().toPoint()-self.pos()
    def mouseMoveEvent(self,event):
        if self.origin is not None:self.move(event.globalPosition().toPoint()-self.origin)
    def mouseReleaseEvent(self,event):self.origin=None
    def mouseDoubleClickEvent(self,event):self.main.restore()
    def closeEvent(self,event):event.ignore();self.main.restore()

def streak_tray_icon(streak: int, completed_today: bool, icon_root=None) -> QIcon:
    """Use the existing flame SVG above a centered streak number."""
    from PySide6.QtCore import QByteArray, QRectF
    from PySide6.QtGui import QFont
    from PySide6.QtSvg import QSvgRenderer
    filename = 'streak_flame_lit.svg' if completed_today else 'streak_flame_unlit.svg'
    svg = Path(icon_root or ROOT / 'assets' / 'icons') / filename
    if not svg.exists(): svg=ROOT/'skins'/'eren_anki'/'icons'/filename
    renderer = QSvgRenderer(QByteArray(svg.read_bytes()))
    if not renderer.isValid():
        raise ValueError(f'Invalid tray flame SVG: {svg}')
    canvas = QPixmap(128, 128)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter, QRectF(22, 2, 84, 86))
    font = QFont('DejaVu Sans')
    font.setPixelSize(38 if streak<100 else 32 if streak<1000 else 26)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor('#ffffff'))
    painter.drawText(QRectF(0, 87, 128, 40), Qt.AlignmentFlag.AlignCenter, str(max(0, streak)))
    painter.end()
    return QIcon(canvas)

class Window(QMainWindow):
    def __init__(self,storage=None,autostart=True):
        super().__init__();self.setWindowTitle('Anki Companion');self.resize(820,730)
        self.storage=Path(storage or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        self.storage.mkdir(parents=True,exist_ok=True)
        self.config_path=self.storage/'connection.json';self.state_path=self.storage/'state.json'
        self.config=json.loads(self.config_path.read_text()) if self.config_path.exists() else {}
        self.current=json.loads(self.state_path.read_text()) if self.state_path.exists() else None
        self.packs=Packs(ROOT/'skins',self.storage/'packs');self.jobs=[];self.syncing=False;self.quitting=False;self.last_key=None
        self.dock=Dock(self);self.tray=QSystemTrayIcon(self)
        icon=streak_tray_icon(0, False);self.setWindowIcon(icon);self.tray.setIcon(icon)
        menu=QMenu();menu.addAction('Open',self.restore);menu.addAction('Compact dock',self.show_dock);menu.addAction('Study',self.study);menu.addSeparator();menu.addAction('Quit',self.quit_app)
        self.tray.setContextMenu(menu);self.tray.activated.connect(lambda reason:self.restore() if reason==QSystemTrayIcon.ActivationReason.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():self.tray.show()
        body=QWidget();self.setCentralWidget(body);box=QVBoxLayout(body);box.setContentsMargins(22,18,22,18);box.setSpacing(12)
        head=QHBoxLayout();title=QLabel('ANKI  /  COMPANION');title.setObjectName('title');head.addWidget(title);head.addStretch()
        connect=QPushButton('Connection');connect.clicked.connect(self.connect_dialog);head.addWidget(connect);box.addLayout(head)
        self.panel=Panel();box.addWidget(self.panel,1)
        self.status=QLabel('Connect your server to begin.');self.status.setWordWrap(True);box.addWidget(self.status)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setTextVisible(False);self.progress.setFixedHeight(7);box.addWidget(self.progress)
        self.count=QLabel('No activity loaded');box.addWidget(self.count)
        form=QFormLayout();self.device=QComboBox();self.parent_deck=QComboBox();self.mode=QComboBox()
        self.mode.addItem('No new cards remaining','new_only');self.mode.addItem('No new, review or due learning cards','new_and_reviews')
        self.device.currentIndexChanged.connect(self.populate_decks)
        form.addRow('Study device',self.device);form.addRow('Parent deck',self.parent_deck);form.addRow('Advance when',self.mode);box.addLayout(form)
        actions=QHBoxLayout();self.study_button=QPushButton('Study next subdeck');self.study_button.setObjectName('primary');self.study_button.clicked.connect(self.study)
        save=QPushButton('Save deck settings');save.clicked.connect(self.save_deck);refresh=QPushButton('Refresh');refresh.clicked.connect(self.refresh)
        actions.addWidget(self.study_button,1);actions.addWidget(save);actions.addWidget(refresh);box.addLayout(actions)
        footer=QHBoxLayout();goals=QPushButton('Lesson & day');goals.clicked.connect(self.goal_dialog);skins=QPushButton('Skins');skins.clicked.connect(self.skin_dialog);compact=QPushButton('Dock');compact.clicked.connect(self.show_dock)
        for b in (goals,skins,compact):footer.addWidget(b)
        box.addLayout(footer);note=QLabel('A lesson maintains your streak. Anki decides which cards are available.');note.setWordWrap(True);note.setObjectName('muted');box.addWidget(note)
        self.update_button=QPushButton('Updates · '+updates.version()['version']);self.update_button.clicked.connect(lambda:self.check_updates(True));box.addWidget(self.update_button)
        self.update_timer=QTimer(self);self.update_timer.timeout.connect(lambda:self.check_updates(False))
        if autostart:self.update_timer.start(15*60*1000);QTimer.singleShot(3000,lambda:self.check_updates(False))
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh)
        if autostart:self.timer.start(5000);QTimer.singleShot(0,self.refresh)

    def client(self):return Client(self.config.get('url','http://127.0.0.1:8765'),self.config.get('token',''),self.config.get('allow_lan_http',False))
    def launch(self,fn,success=None):
        job=Job(fn,self);self.jobs.append(job)
        job.succeeded.connect(success or (lambda result:self.refresh()))
        job.failed.connect(lambda msg:self.status.setText('Action failed: '+msg))
        job.finished.connect(lambda:self.jobs.remove(job));job.finished.connect(job.deleteLater);job.start();return job
    def refresh(self):
        if self.syncing or not self.config.get('token'):return
        self.syncing=True
        def fetch():
            online=True;error=''
            try:
                value=self.client().request('/v1/state');write_json(self.state_path,value)
            except Exception as exc:
                if not self.state_path.exists():raise
                value=json.loads(self.state_path.read_text());online=False;error=str(exc)
            line=value['lineup'];identity=line['skin_id'];version=line['skin_version']
            if (identity,version) not in self.packs.list():
                with tempfile.NamedTemporaryFile(suffix='.zip',delete=False) as f:path=Path(f.name);f.write(self.client().request(f'/v1/skins/{identity}/{version}/pack.zip',raw=True))
                try:self.packs.install(path)
                finally:path.unlink(missing_ok=True)
            skin,root=self.packs.get(identity,version);now=int(time.time()*1000)
            current_day=study_day(now,value['settings']['timezone'],value['settings']['rollover_minute'])
            old_day=current_day!=line['date']
            if old_day:line=daily_lineup(current_day,skin,value['seed'])
            case=scene(skin,line,now,value['settings'],value['completed'] and not old_day,value['streak'])
            key=json.dumps(case,sort_keys=True);frame=None;warning=None
            if key!=self.last_key:
                with tempfile.TemporaryDirectory() as tmp:
                    engine=WidgetEngine(root,tmp);frame=engine.render(case,tmp,include_warning=False).read_bytes()
                    import io
                    b=io.BytesIO();engine.icon('warning_badge',58,58).save(b,format='PNG');warning=b.getvalue()
            minute=int(case['time'][:2])*60+int(case['time'][3:])
            return value,online,error,key,frame,warning,not case['completed'] and minute>=skin['style']['warning_start_minute'],old_day
        job=self.launch(fetch,self.receive);job.failed.connect(lambda _:setattr(self,'syncing',False))
    def receive(self,result):
        value,online,error,key,frame,warning,warn,old_day=result;self.syncing=False
        old_device=self.device.currentData();was_first=self.current is None or self.device.count()==0;self.current=value
        lit=bool(value['completed']) and not old_day
        tray_icon=streak_tray_icon(int(value['streak']),lit)
        self.tray.setIcon(tray_icon);self.setWindowIcon(tray_icon)
        self.tray.setToolTip(f"{value['streak']} day streak · {'today complete' if lit else 'today incomplete'}")
        if frame:
            self.panel.set_frame(frame,warning,warn);self.dock.panel.set_frame(frame,warning,warn);self.last_key=key
        age=max(0,int((time.time()*1000-value['server_time_ms'])/1000))
        self.status.setText(('Connected · last server update '+str(age)+'s ago') if online else ('Offline · last server update '+str(age)+'s ago'+(' · new day is not yet synced' if old_day else '')))
        p=value['progress'];g=value['policy'];ratio=min(p['answers']/g['lesson_answers'],p['duration_ms']/g['lesson_ms'] if g['lesson_ms'] else 1)
        self.progress.setValue(min(100,int(ratio*100)))
        remaining=max(0,g['lesson_answers']-p['answers']);percent=min(100,p['answers']*100//g['lesson_answers'])
        self.count.setText(f"{p['answers']}/{g['lesson_answers']} · {percent}% · {remaining} remaining  ·  {p['duration_ms']//1000}/{g['lesson_ms']//1000} active seconds")
        devices=[(d['label'],d['device_id']) for d in value['devices']]
        existing=[(self.device.itemText(i),self.device.itemData(i)) for i in range(self.device.count())]
        if devices!=existing:
            self.device.blockSignals(True);self.device.clear()
            for label,identity in devices:self.device.addItem(label,identity)
            index=self.device.findData(old_device);self.device.setCurrentIndex(max(0,index));self.device.blockSignals(False);self.populate_decks()
        if was_first:self.mode.setCurrentIndex(self.mode.findData(value['settings']['clearance']))
    def populate_decks(self):
        if not self.current:return
        selected=self.parent_deck.currentData() or self.current['settings']['parent_deck_id'];self.parent_deck.clear()
        device=next((d for d in self.current['devices'] if d['device_id']==self.device.currentData()),None)
        if device:
            for deck in sorted(device['decks'],key=lambda d:d['name'].casefold()):self.parent_deck.addItem(deck['name'],deck['id'])
        idx=self.parent_deck.findData(selected);self.parent_deck.setCurrentIndex(max(0,idx))
    def save_deck(self):
        if not self.current:return
        value=dict(self.current['settings'],parent_deck_id=self.parent_deck.currentData() or '',clearance=self.mode.currentData())
        self.launch(lambda:self.client().request('/v1/settings','PUT',value))
    def study(self):
        if not self.current:return
        identity=self.device.currentData();deck=self.current['next_decks'].get(identity)
        device=next((d for d in self.current['devices'] if d['device_id']==identity),None)
        if not deck or not device:self.status.setText('Choose a parent deck and connect Anki first.');return
        if int(time.time()*1000)-device['updated_ms']>120000:self.status.setText('Study device is offline. Open Anki on that device and refresh.');return
        self.launch(lambda:self.client().request('/v1/commands','POST',dict(device_id=identity,action='study',deck_id=deck['id'])),lambda _:self.status.setText('Study request sent to '+device['label']))
    def connect_dialog(self):
        dialog=QDialog(self);dialog.setWindowTitle('Connect companion server');form=QFormLayout(dialog)
        url=QLineEdit(self.config.get('url','http://127.0.0.1:8765'));token=QLineEdit(self.config.get('token',''));token.setEchoMode(QLineEdit.EchoMode.Password)
        lan=QCheckBox('Allow HTTP on a trusted local network');lan.setChecked(self.config.get('allow_lan_http',False))
        form.addRow('Server URL',url);form.addRow('Pairing token',token);form.addRow(lan)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
        if dialog.exec():
            try:Client(url.text(),token.text(),lan.isChecked())
            except ValueError as exc:QMessageBox.warning(self,'Connection',str(exc));return
            self.config=dict(url=url.text().rstrip('/'),token=token.text().strip(),allow_lan_http=lan.isChecked());write_json(self.config_path,self.config,True);self.refresh()
    def goal_dialog(self):
        if not self.current:return
        s=self.current['settings'];dialog=QDialog(self);dialog.setWindowTitle('Lesson & study day');form=QFormLayout(dialog)
        answers=QSpinBox();answers.setRange(1,10000);answers.setValue(s['lesson_answers'])
        seconds=QSpinBox();seconds.setRange(0,36000);seconds.setValue(s['lesson_ms']//1000)
        tz=QLineEdit(s['timezone']);rollover=QSpinBox();rollover.setRange(0,1439);rollover.setValue(s['rollover_minute'])
        for label,field in [('Answered cards',answers),('Active seconds',seconds),('IANA timezone',tz),('Rollover minute after midnight',rollover)]:form.addRow(label,field)
        text=QLabel('Goals take effect on the next new study day. The initial 10 answers / 300 seconds is provisional. Timezone and rollover lock after the first review.');text.setWordWrap(True);form.addRow(text)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
        if dialog.exec():
            payload=dict(s,lesson_answers=answers.value(),lesson_ms=seconds.value()*1000,timezone=tz.text(),rollover_minute=rollover.value())
            self.launch(lambda:self.client().request('/v1/settings','PUT',payload))
    def skin_dialog(self):
        if not self.current:return
        def show(result):
            dialog=QDialog(self);dialog.setWindowTitle('Skins');box=QVBoxLayout(dialog);combo=QComboBox()
            for skin in result['skins']:combo.addItem(skin['name']+' · '+skin['version'],skin)
            box.addWidget(combo);note=QLabel('Changes take effect on the next study day.');box.addWidget(note)
            activate=QPushButton('Use selected skin');import_button=QPushButton('Import skin ZIP');box.addWidget(activate);box.addWidget(import_button)
            def use():
                skin=combo.currentData();s=dict(self.current['settings'],skin_id=skin['id'],skin_version=skin['version']);self.launch(lambda:self.client().request('/v1/settings','PUT',s));dialog.accept()
            def upload():
                path,_=QFileDialog.getOpenFileName(dialog,'Skin ZIP','','ZIP archives (*.zip)')
                if path:
                    if Path(path).stat().st_size>50*1024*1024:self.status.setText('ZIP exceeds 50 MiB');return
                    self.launch(lambda:self.client().request('/v1/skins/import','POST',Path(path).read_bytes(),content_type='application/zip'));dialog.accept()
            activate.clicked.connect(use);import_button.clicked.connect(upload);dialog.exec()
        self.launch(lambda:self.client().request('/v1/skins'),show)
    def show_dock(self):self.hide();self.dock.show();self.dock.raise_()
    def check_updates(self,interactive=False):
        if not self.config.get('token'):return
        platform='windows' if sys.platform=='win32' else 'source'
        def received(release):
            if not release.get('configured'):
                if interactive:
                    from PySide6.QtWidgets import QInputDialog
                    repository,ok=QInputDialog.getText(self,'GitHub update source','GitHub repository (owner/name):')
                    if ok and repository.strip() and self.current:
                        payload=dict(self.current['settings'],update_repository=repository.strip())
                        self.launch(lambda:self.client().request('/v1/settings','PUT',payload),lambda _:self.check_updates(True))
                return
            self.update_button.setText(('Update to '+release['version']) if release.get('available') else ('Up to date · '+updates.version()['version']))
            if release.get('available'):
                if not interactive:
                    if self.tray.isVisible():self.tray.showMessage('Anki Companion update','Version '+release['version']+' is ready. Open the app and click Update.')
                    return
                text=release.get('notes','')[:1500]+'\n\nSource commit: '+release.get('commit','')
                if QMessageBox.question(self,'Update to '+release['version'],text+'\n\nDownload and update?')==QMessageBox.StandardButton.Yes:
                    def ready(path):
                        try:updates.install(path);self.quit_app()
                        except ValueError as exc:self.status.setText(str(exc)+' Downloaded to '+str(path))
                    self.status.setText('Downloading and verifying update…')
                    self.launch(lambda:updates.download(self.client(),release,self.storage/'updates'),ready)
            elif interactive:self.status.setText(release.get('message','No newer release'))
        self.launch(lambda:self.client().request('/v1/updates/'+platform+'?current='+updates.version()['version']+('&force=true' if interactive else '')),received)
    def restore(self):self.dock.hide();self.showNormal();self.raise_();self.activateWindow()
    def closeEvent(self,event):
        if self.quitting:event.accept();return
        event.ignore()
        self.show_dock()
    def quit_app(self):
        self.quitting=True;self.timer.stop();self.update_timer.stop();self.hide();self.dock.hide();self.tray.hide()
        # Let network workers finish before destroying their QThread objects.
        if self.jobs:QTimer.singleShot(100,self.quit_app)
        else:QApplication.instance().quit()

STYLE='''QWidget{background:#121418;color:#eee6db;font-family:"DejaVu Sans";font-size:13px} QLabel#title{font-size:18px;font-weight:700;letter-spacing:2px} QLabel#muted{color:#9a9da3;font-size:11px} QPushButton,QComboBox,QLineEdit,QSpinBox{background:#22252b;border:1px solid #363a42;border-radius:7px;padding:9px} QPushButton:hover{border-color:#f19a4c} QPushButton#primary{background:#ee9147;color:#17120e;font-weight:700} QProgressBar{border:0;background:#2e3036;border-radius:3px} QProgressBar::chunk{background:#ef944a;border-radius:3px}'''

def main():
    app=QApplication(sys.argv);app.setApplicationName('AnkiCompanion');app.setOrganizationName('AnkiCompanion');app.setQuitOnLastWindowClosed(False);app.setStyleSheet(STYLE)
    window=Window();window.show();sys.exit(app.exec())

if __name__=='__main__':main()
