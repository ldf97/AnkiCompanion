"""Anki hooks run on the GUI thread; only network/outbox I/O runs in the worker."""
import json, time, uuid, threading, sqlite3, os
from urllib.parse import quote
from pathlib import Path
from aqt import mw, gui_hooks
from aqt.qt import QTimer
from .transport import Client
from .rules import next_deck
from .history import reconcile

NAME=__package__; controller=None

class Bridge:
    def __init__(self):
        self.config=mw.addonManager.getConfig(NAME) or {}
        self.discover_local_token()
        self.applied_revision=int(self.config.get('applied_revision',0))
        if not self.config.get('device_id'):
            self.config['device_id']='desktop-'+uuid.uuid4().hex
            mw.addonManager.writeConfig(NAME,self.config)
        self.file=Path(mw.pm.profileFolder())/'anki-companion-outbox.sqlite3'
        self.lock=threading.RLock();self.stopped=False;self.busy=False;self.syncing=False
        self.collection_synced_ms=0;self.last_sync=0;self.last_scan=0;self.review_dirty=False;self.settings={};self.backfill_active=True;self.backfill_pending=False;self.high_water=int((time.time()-370*86400)*1000)
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,payload TEXT NOT NULL,sent INTEGER NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS undo(id TEXT PRIMARY KEY,sent INTEGER NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY);')
        self.timer=QTimer(mw);self.timer.timeout.connect(self.tick);self.timer.start(2000)
        QTimer.singleShot(1000,self.tick)
    def discover_local_token(self):
        if self.config.get('token'):return
        home=Path(os.environ.get('LOCALAPPDATA') or
                  (Path.home()/'AppData'/'Local'))/'AnkiCompanion'/'server'/'token.txt'
        try:
            token=home.read_text(encoding='utf-8').strip()
            if len(token)>=16:
                self.config['token']=token
                self.config['server_url']='http://127.0.0.1:8765'
                self.config['allow_lan_http']=False
                mw.addonManager.writeConfig(NAME,self.config)
        except OSError:
            pass

    def db(self):return sqlite3.connect(self.file,timeout=0.5)
    def stop(self):self.stopped=True;self.timer.stop()
    def client(self):return Client(self.config['server_url'],self.config['token'],self.config.get('allow_lan_http',False))
    def scan(self):
        if not mw.col:return
        collection=self.config.get('collection_id','primary')
        if self.backfill_pending and not self.backfill_active:
            self.high_water=int((time.time()-370*86400)*1000)
            self.backfill_active=True;self.backfill_pending=False
        with self.lock,self.db() as db:
            before=self.high_water
            self.high_water=reconcile(mw.col.db,db,collection,self.high_water,int((time.time()-3600)*1000))
            if self.high_water==before:self.backfill_active=False
    def collection_synced(self):
        # A native sync every ten seconds must not continually reset a large
        # paginated history before the scan has reached its newer rows.
        self.backfill_pending=True
        self.tick()
    def decks(self):
        result=[]
        def walk(node,prefix=''):
            name=(prefix+'::' if prefix else '')+node.name if node.name else prefix
            if node.deck_id:
                result.append(dict(id=str(node.deck_id),name=name,new=node.new_count,review=node.review_count,learning=node.learn_count))
            for child in node.children:walk(child,name)
        walk(mw.col.sched.deck_due_tree())
        return result
    def tick(self):
        if self.stopped or self.busy or self.syncing or not mw.col:return
        if not self.config.get('token'):self.discover_local_token()
        if not self.config.get('token'):return
        try:
            # Never scan the full history on every five-second GUI timer.
            # A review wakes it immediately; idle history reads are throttled.
            if self.review_dirty or time.time()-self.last_scan>=20:
                self.scan();self.last_scan=time.time()
            decks=self.decks()
        except Exception as exc:print('Anki Companion scan:',exc);return
        self.busy=True
        def worker():
            error=None;commands=[];settings={};native={}
            try:
                api=self.client()
                with self.lock,self.db() as db:
                    pending=db.execute('SELECT id,payload FROM outbox WHERE sent=0 LIMIT 1000').fetchall()
                    undo=[r[0] for r in db.execute('SELECT id FROM undo WHERE sent=0 LIMIT 1000')]
                if pending:
                    api.request('/v1/events','POST',{'device_id':self.config['device_id'],'events':[json.loads(p) for i,p in pending]})
                    with self.lock,self.db() as db:db.executemany('UPDATE outbox SET sent=1 WHERE id=?',[(i,) for i,p in pending])
                if undo:
                    api.request('/v1/events/retract','POST',{'ids':undo,'device_id':self.config['device_id']})
                    with self.lock,self.db() as db:db.executemany('UPDATE undo SET sent=1 WHERE id=?',[(i,) for i in undo])
                api.request('/v1/snapshots','POST',dict(device_id=self.config['device_id'],
                    label=self.config.get('device_label','Anki Desktop'),decks=decks,
                    collection_id=self.config.get('collection_id','primary'),
                    applied_revision=self.applied_revision,
                    sync_status='native Anki sync' if self.collection_synced_ms else 'not yet synced',
                    collection_synced_ms=self.collection_synced_ms))
                query='?device_id='+quote(self.config['device_id'],safe='')+'&collection_id='+quote(self.config.get('collection_id','primary'),safe='')
                state=api.request('/v1/state'+query)
                settings=state['settings'];native=state.get('native_sync',{})
                commands=api.request('/v1/commands/'+self.config['device_id'])['commands']
            except Exception as exc:error=str(exc)
            if not self.stopped:mw.taskman.run_on_main(lambda:self.received(commands,settings,native,error))
        threading.Thread(target=worker,daemon=True).start()
    def received(self,commands,settings,native,error):
        self.busy=False
        if self.stopped or not mw.col:return
        if settings:self.settings=settings
        if error:print('Anki Companion offline:',error)
        for command in commands:
            # Never interrupt an active answer or launch another profile's collection.
            if mw.state not in ('deckBrowser','overview'):continue
            with self.lock,self.db() as db:
                seen=db.execute('SELECT 1 FROM commands WHERE id=?',(command['id'],)).fetchone()
            if seen:
                threading.Thread(target=self.ack,args=(command['id'],),daemon=True).start()
                continue
            if self.syncing:break
            def applied(command=command):
                if command['action']=='study':self.open_deck(command['deck_id'])
                with self.lock,self.db() as db:db.execute('INSERT OR IGNORE INTO commands VALUES (?)',(command['id'],))
                threading.Thread(target=self.ack,args=(command['id'],),daemon=True).start()
            self.sync_then(applied)
        # Versioned remote changes: one native sync then ACK. Offline clients
        # keep a durable revision cursor and resume automatically on startup.
        if native.get('pending') and self.config.get('auto_sync',True):
            required=int(native.get('revision',0))
            if mw.state in ('deckBrowser','overview'):
                self.sync_then(lambda:self.mark_applied(required))
            # Never reset the active review card out from under the user.
            return
        if self.config.get('auto_sync',True) and mw.state in ('deckBrowser','overview','review') and time.time()-self.last_sync>(2 if self.review_dirty else 10):
            self.sync_then(lambda:None)

    def mark_applied(self,version):
        if version>self.applied_revision:
            self.applied_revision=version
            self.config['applied_revision']=version
            mw.addonManager.writeConfig(NAME,self.config)
    def ack(self,identity):
        try:self.client().request('/v1/commands/'+self.config['device_id']+'/'+identity+'/ack','POST',{})
        except Exception:pass
    def sync_then(self,after):
        if self.syncing:return
        auth=mw.pm.sync_auth()
        if not self.config.get('auto_sync',True) or not auth:
            print('Anki Companion: configure native Anki sync before automatic handoff')
            return
        self.syncing=True;self.last_sync=time.time()
        # Do not emit Anki's global sync hooks manually; they can invoke
        # unrelated add-ons and cause re-entrant callbacks.
        def finished(future):
            self.syncing=False
            if self.stopped or not mw.col:return
            try:
                result=future.result()
                if result.new_endpoint:mw.pm.set_current_sync_url(result.new_endpoint)
                mw.pm.set_host_number(result.host_number)
                if result.required!=result.NO_CHANGES:
                    print('Anki Companion: complete initial/full sync in Anki before study handoff')
                    return
                self.collection_synced_ms=int(time.time()*1000);self.review_dirty=False
                mw.col._load_scheduler();mw.col.models._clear_cache()
                if mw.state in ('deckBrowser','overview'):
                    mw.reset()
                after();self.tick()
            except Exception as exc:print('Anki Companion native sync failed:',exc)
        # Anki owns the collection operation and scheduling merge; never copy its DB.
        try:
            # No blocking progress dialog while answering cards. Anki's own
            # task manager executes the native sync on a collection worker.
            mw.taskman.run_in_background(
                lambda:mw.col.sync_collection(auth,mw.pm.media_syncing_enabled()),
                finished,uses_collection=True)
        except Exception as exc:self.syncing=False;print('Anki Companion sync:',exc)
    def open_deck(self,identity):
        if self.stopped or not mw.col or not identity:return
        # Recompute after collection sync rather than opening a now-cleared deck.
        selected=next_deck(self.decks(),self.settings.get('parent_deck_id',''),self.settings.get('clearance','new_and_reviews'))
        if not selected:return
        identity=selected['id']
        mw.col.decks.select(int(identity));mw.moveToState('review')
    def answered(self,*args):QTimer.singleShot(100,self.after_answer)
    def after_answer(self):
        if self.stopped or not mw.col:return
        try:
            self.review_dirty=True
            self.tick()
            if mw.state!='review' or not self.settings.get('parent_deck_id'):return
            decks=self.decks();current=str(mw.col.decks.current()['id'])
            selected=next((d for d in decks if d['id']==current),None)
            if selected is None:return
            mode=self.settings.get('clearance','new_and_reviews')
            cleared=selected['new']==0 and (mode=='new_only' or selected['review']+selected['learning']==0)
            parent=next((d for d in decks if d['id']==self.settings['parent_deck_id']),None)
            if cleared and parent and (selected['name']==parent['name'] or selected['name'].startswith(parent['name']+'::')):
                target=next_deck(decks,parent['id'],mode)
                if target and target['id']!=current:mw.col.decks.select(int(target['id']));mw.reset()
        except Exception as exc:print('Anki Companion advance:',exc)

def opened():
    global controller
    try:
        if controller:controller.stop()
        controller=Bridge()
    except Exception as exc:
        # A companion integration must NEVER prevent Anki from starting.
        print('Anki Companion initialization disabled:',exc)
        controller=None
def closed():
    global controller
    if controller:controller.stop();controller=None
def answered(*args):
    if controller:
        try:controller.answered(*args)
        except Exception as exc:print('Anki Companion answer callback:',exc)
def synced(*args):
    if controller:
        try:controller.collection_synced()
        except Exception as exc:print('Anki Companion sync callback:',exc)
# All GUI hooks are registered exactly once by the guarded __init__.py.
# Registering them again here would duplicate startup and review callbacks.
