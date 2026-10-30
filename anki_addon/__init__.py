"""Anki hooks run on the GUI thread; only network/outbox I/O runs in the worker."""
import json, time, uuid, threading, sqlite3
from pathlib import Path
from aqt import mw, gui_hooks
from aqt.qt import QTimer
from .transport import Client
from .rules import next_deck
from .history import reconcile

NAME=__name__; controller=None

class Bridge:
    def __init__(self):
        self.config=mw.addonManager.getConfig(NAME) or {}
        if not self.config.get('device_id'):
            self.config['device_id']='desktop-'+uuid.uuid4().hex
            mw.addonManager.writeConfig(NAME,self.config)
        self.file=Path(mw.pm.profileFolder())/'anki-companion-outbox.sqlite3'
        self.lock=threading.RLock();self.stopped=False;self.busy=False;self.syncing=False
        self.collection_synced_ms=0;self.last_sync=0;self.review_dirty=False;self.settings={};self.high_water=int((time.time()-370*86400)*1000)
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,payload TEXT NOT NULL,sent INTEGER NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS undo(id TEXT PRIMARY KEY,sent INTEGER NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY);')
        self.timer=QTimer(mw);self.timer.timeout.connect(self.tick);self.timer.start(5000)
        QTimer.singleShot(1000,self.tick)
    def db(self):return sqlite3.connect(self.file,timeout=20)
    def stop(self):self.stopped=True;self.timer.stop()
    def client(self):return Client(self.config['server_url'],self.config['token'],self.config.get('allow_lan_http',False))
    def scan(self):
        if not mw.col:return
        collection=self.config.get('collection_id','primary')
        with self.lock,self.db() as db:
            self.high_water=reconcile(mw.col.db,db,collection,self.high_water,int((time.time()-3600)*1000))
    def collection_synced(self):
        self.high_water=int((time.time()-370*86400)*1000)
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
        if self.stopped or self.busy or self.syncing or not mw.col or not self.config.get('token'):return
        try:self.scan();decks=self.decks()
        except Exception as exc:print('Anki Companion scan:',exc);return
        self.busy=True
        def worker():
            error=None;commands=[];settings={}
            try:
                api=self.client()
                with self.lock,self.db() as db:
                    pending=db.execute('SELECT id,payload FROM outbox WHERE sent=0 LIMIT 1000').fetchall()
                    undo=[r[0] for r in db.execute('SELECT id FROM undo WHERE sent=0 LIMIT 1000')]
                if pending:
                    api.request('/v1/events','POST',{'device_id':self.config['device_id'],'events':[json.loads(p) for i,p in pending]})
                    with self.lock,self.db() as db:db.executemany('UPDATE outbox SET sent=1 WHERE id=?',[(i,) for i,p in pending])
                if undo:
                    api.request('/v1/events/retract','POST',{'ids':undo})
                    with self.lock,self.db() as db:db.executemany('UPDATE undo SET sent=1 WHERE id=?',[(i,) for i in undo])
                api.request('/v1/snapshots','POST',dict(device_id=self.config['device_id'],label=self.config.get('device_label','Anki Desktop'),decks=decks,sync_status='native Anki sync',collection_synced_ms=self.collection_synced_ms))
                settings=api.request('/v1/state')['settings']
                commands=api.request('/v1/commands/'+self.config['device_id'])['commands']
            except Exception as exc:error=str(exc)
            if not self.stopped:mw.taskman.run_on_main(lambda:self.received(commands,settings,error))
        threading.Thread(target=worker,daemon=True).start()
    def received(self,commands,settings,error):
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
        if self.config.get('auto_sync',True) and mw.state in ('deckBrowser','overview','review') and time.time()-self.last_sync>(2 if self.review_dirty else 10):
            self.sync_then(lambda:None)
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
        gui_hooks.sync_will_start()
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
                gui_hooks.sync_did_finish();mw.reset();after();self.tick()
            except Exception as exc:print('Anki Companion native sync failed:',exc)
        # Anki owns the collection operation and scheduling merge; never copy its DB.
        try:mw.taskman.with_progress(lambda:mw.col.sync_collection(auth,mw.pm.media_syncing_enabled()),finished)
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
    if controller:controller.stop()
    controller=Bridge()
def closed():
    global controller
    if controller:controller.stop();controller=None
def answered(*args):
    if controller:controller.answered(*args)
def synced(*args):
    if controller:controller.collection_synced()
gui_hooks.profile_did_open.append(opened)
gui_hooks.profile_will_close.append(closed)
gui_hooks.reviewer_did_answer_card.append(answered)
gui_hooks.sync_did_finish.append(synced)
