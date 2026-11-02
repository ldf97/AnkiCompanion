"""Anki hooks run on the GUI thread; only network/outbox I/O runs in the worker."""
import json, time, uuid, threading, sqlite3, os
from urllib.parse import quote
from pathlib import Path
from aqt import mw, gui_hooks
from aqt.qt import QTimer
from .transport import Client
from .rules import next_deck
from .history import reconcile
from .review_epoch import ReviewEpoch

NAME=__package__; controller=None

class Bridge:
    def __init__(self):
        self.config=mw.addonManager.getConfig(NAME) or {}
        self.discover_local_token()
        self.applied_revision=int(self.config.get('applied_revision',0))
        self.native_sync_error=str(self.config.get('native_sync_error',''))
        self.native_collision_blocked=False
        self.pending_ticket=self.config.get('native_upload_ticket','')
        self.confirmed_ticket=self.config.get('native_confirmed_ticket','')
        if not self.config.get('device_id'):
            self.config['device_id']='desktop-'+uuid.uuid4().hex
            mw.addonManager.writeConfig(NAME,self.config)
        self.file=Path(mw.pm.profileFolder())/'anki-companion-outbox.sqlite3'
        self.lock=threading.RLock();self.stopped=False;self.busy=False;self.syncing=False
        self.next_native_attempt_at=0;self.sync_attempt_failures=0
        self.undo_requested=False
        self.collection_synced_ms=0;self.last_sync=0;self.last_scan=0;
        self.answers=ReviewEpoch();self.stop_event=threading.Event();self.settings={};self.backfill_active=True;self.backfill_pending=False;self.high_water=int((time.time()-370*86400)*1000)
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,payload TEXT NOT NULL,sent INTEGER NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS undo(id TEXT PRIMARY KEY,sent INTEGER NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY);')
        self.timer=QTimer(mw);self.timer.timeout.connect(self.tick);self.timer.start(2000)
        QTimer.singleShot(1000,self.tick)
        self.watcher=threading.Thread(target=self.watch_changes,daemon=True)
        self.watcher.start()
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
    def stop(self):
        self.stopped=True;self.stop_event.set();self.timer.stop()
    def watch_changes(self):
        # A push-like wakeup without credential-bearing broadcasts or a busy
        # loop. The cursor lives on the server so reconnects do not lose updates.
        sequence=None
        while not self.stop_event.is_set():
            try:
                api=self.client()
                scope='&device_id='+quote(self.config['device_id'],safe='')+'&collection_id='+quote(self.config.get('collection_id','primary'),safe='')
                query='/v1/changes?since='+str(sequence or 0)+'&wait_ms='+('0' if sequence is None else '3500')+scope
                state=api.request(query)
                # Suppressed self-events move the cursor but do not wake the
                # originating Anki reviewer's costly scan/native sync.
                changed=sequence is not None and (state.get('changed',False) or state.get('reset',False))
                sequence=state['sequence']
                if changed and not self.stopped:
                    mw.taskman.run_on_main(lambda:self.tick() if not self.stopped else None)
            except Exception:
                sequence=None
                self.stop_event.wait(2)

    def client(self):return Client(self.config['server_url'],self.config['token'],self.config.get('allow_lan_http',False))
    def scan(self):
        if not mw.col:return
        collection=self.config.get('collection_id','primary')
        if self.backfill_pending and not self.backfill_active:
            self.high_water=int((time.time()-370*86400)*1000)
            self.backfill_active=True;self.backfill_pending=False
        with self.lock,self.db() as db:
            before=self.high_water
            self.high_water=reconcile(mw.col.db,db,collection,self.high_water,int((time.time()-3600)*1000),
                allow_retractions=not self.syncing and (self.collection_synced_ms>0 or self.undo_requested))
            if self.high_water==before:self.backfill_active=False
    def collection_synced(self):
        # Native Anki completed a user-initiated resolution; release a previous
        # full-sync conflict backoff, but still require a new verified receipt.
        self.next_native_attempt_at=0
        self.sync_attempt_failures=0
        self.native_sync_error=''
        self.config['native_sync_error']=''
        mw.addonManager.writeConfig(NAME,self.config)
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
            if self.answers.needs_scan or self.undo_requested or time.time()-self.last_scan>=20:
                with self.lock,self.db() as db:
                    prior_undos=db.execute('SELECT COUNT(*) FROM undo WHERE sent=0').fetchone()[0]
                self.scan();self.last_scan=time.time()
                with self.lock,self.db() as db:
                    latest_undos=db.execute('SELECT COUNT(*) FROM undo WHERE sent=0').fetchone()[0]
                if self.undo_requested and latest_undos>prior_undos:
                    # The undo really removed at least one review-log row.
                    # Dispatch a native synchronization generation, but do NOT
                    # retract the review from the streak-accountability ledger.
                    self.answers.answer()
                self.undo_requested=False
                self.answers.scan_complete()
            decks=self.decks()
        except Exception as exc:print('Anki Companion scan:',exc);return
        captured_generation=self.answers.scanned
        self.busy=True
        def worker():
            error=None;commands=[];settings={};native={};source_ticket='';uploaded_generation=0
            try:
                api=self.client()
                with self.lock,self.db() as db:
                    pending=db.execute('SELECT id,payload FROM outbox WHERE sent=0 LIMIT 1000').fetchall()
                    undo=[r[0] for r in db.execute('SELECT id FROM undo WHERE sent=0 LIMIT 1000')]
                if pending:
                    receipt=api.request('/v1/events','POST',{'device_id':self.config['device_id'],'events':[json.loads(p) for i,p in pending]})
                    source_ticket=receipt.get('native_upload_tickets',{}).get(self.config.get('collection_id','primary'),'')
                    with self.lock,self.db() as db:db.executemany('UPDATE outbox SET sent=1 WHERE id=?',[(i,) for i,p in pending])
                if undo:
                    api.request('/v1/events/retract','POST',{'ids':undo,'device_id':self.config['device_id']})
                    with self.lock,self.db() as db:db.executemany('UPDATE undo SET sent=1 WHERE id=?',[(i,) for i in undo])
                # The network batch is capped at 1000. An acknowledgment of
                # that batch MUST NOT claim the entire generation is uploaded
                # if more review/undo events are still on disk.
                with self.lock,self.db() as db:
                    has_unsent = bool(db.execute('SELECT 1 FROM outbox WHERE sent=0 LIMIT 1').fetchone())
                    has_undos = bool(db.execute('SELECT 1 FROM undo WHERE sent=0 LIMIT 1').fetchone())
                if not has_unsent and not has_undos:
                    uploaded_generation=captured_generation
                api.request('/v1/snapshots','POST',dict(device_id=self.config['device_id'],
                    label=self.config.get('device_label','Anki Desktop'),decks=decks,
                    collection_id=self.config.get('collection_id','primary'),
                    applied_revision=self.applied_revision,
                    native_upload_ticket=self.confirmed_ticket,
                    sync_status=self.native_sync_error or ('native Anki sync' if self.collection_synced_ms else 'not yet synced'),
                    collection_synced_ms=self.collection_synced_ms))
                query='?device_id='+quote(self.config['device_id'],safe='')+'&collection_id='+quote(self.config.get('collection_id','primary'),safe='')
                state=api.request('/v1/state'+query)
                settings=state['settings'];native=state.get('native_sync',{})
                source_ticket=native.get('outgoing_ticket') or source_ticket
                commands=api.request('/v1/commands/'+self.config['device_id'])['commands']
            except Exception as exc:error=str(exc)
            if not self.stopped:mw.taskman.run_on_main(lambda:self.received(commands,settings,native,source_ticket,uploaded_generation,error))
        threading.Thread(target=worker,daemon=True).start()
    def received(self,commands,settings,native,source_ticket,uploaded_generation,error):
        self.busy=False
        if uploaded_generation:self.answers.upload_complete(uploaded_generation)
        if source_ticket and source_ticket!=self.confirmed_ticket:
            self.pending_ticket=source_ticket
            self.config['native_upload_ticket']=source_ticket
            mw.addonManager.writeConfig(NAME,self.config)
        if not source_ticket and self.confirmed_ticket and not error:
            self.confirmed_ticket=''
            self.config['native_confirmed_ticket']=''
            mw.addonManager.writeConfig(NAME,self.config)
        if self.stopped or not mw.col:return
        if settings:self.settings=settings
        if error:print('Anki Companion offline:',error)
        self.native_collision_blocked=bool(native.get('conflicted',False))
        if self.native_collision_blocked:
            self.native_sync_error='Native review-ID collision: two devices assigned one review ID to different cards; automatic scheduling sync deferred. Activity and outbox preserved.'
            self.config['native_sync_error']=self.native_sync_error
            mw.addonManager.writeConfig(NAME,self.config)
            print('Anki Companion:',self.native_sync_error)
            return
        if self.native_sync_error.startswith('Native review-ID collision:'):
            self.native_sync_error=''
            self.config['native_sync_error']=''
            mw.addonManager.writeConfig(NAME,self.config)
        # A study command cannot open a deck based on an old native collection.
        # Complete the remote revision first; the unacknowledged command will be
        # fetched again by tick() after that synchronization succeeds.
        if native.get('pending') and self.config.get('auto_sync',True):
            required=int(native.get('revision',0))
            if mw.state in ('deckBrowser','overview'):
                self.sync_then(lambda:self.mark_applied(required))
            # During a review session, don't interrupt an active card. Retain
            # the server's pending receipt for the next safe state transition.
            return
        for command in commands:
            if mw.state not in ('deckBrowser','overview'):continue
            with self.lock,self.db() as db:
                seen=db.execute('SELECT 1 FROM commands WHERE id=?',(command['id'],)).fetchone()
            if seen:
                threading.Thread(target=self.ack,args=(command['id'],),daemon=True).start()
                continue
            if self.syncing:break
            def applied(command=command):
                if command['action']=='study':
                    self.verify_study_handoff(command)
                    return
                with self.lock,self.db() as db:db.execute('INSERT OR IGNORE INTO commands VALUES (?)',(command['id'],))
                threading.Thread(target=self.ack,args=(command['id'],),daemon=True).start()
            self.sync_then(applied)
        if (not error and self.config.get('auto_sync',True) and
                not self.answers.needs_scan and self.answers.uploaded>=self.answers.answered and
                mw.state in ('deckBrowser','overview','review') and
                time.time()-self.last_sync>(2 if self.answers.needs_sync else 10)):
            self.sync_then(lambda:None)

    def verify_study_handoff(self,command):
        """Never open a card until the just-synced native collection is current.

        Network reads run on a worker. An unacknowledged server command survives
        retries, sleep and process restart. A newer remote revision or offline
        server defers study rather than presenting potentially stale cards.
        """
        if (self.stopped or self.native_collision_blocked or
                self.answers.needs_sync or self.answers.needs_scan):
            self.tick()
            return
        self.busy=True
        def check():
            ready=False
            try:
                collection=self.config.get('collection_id','primary')
                path='/v1/state?device_id='+quote(self.config['device_id'],safe='')+'&collection_id='+quote(collection,safe='')
                state=self.client().request(path)
                native=state['native_sync']
                ready=(not native.get('pending') and not native.get('outgoing_ticket') and
                       not self.native_sync_error and not self.answers.needs_sync)
            except Exception as exc:
                print('Anki Companion study handoff deferred:',exc)
            def finish():
                self.busy=False
                if self.stopped or not mw.col:return
                if ready and mw.state in ('deckBrowser','overview') and not self.answers.needs_sync:
                    self.open_deck(command['deck_id'])
                    with self.lock,self.db() as db:db.execute('INSERT OR IGNORE INTO commands VALUES (?)',(command['id'],))
                    threading.Thread(target=self.ack,args=(command['id'],),daemon=True).start()
                else:
                    print('Anki Companion: study handoff deferred until scheduling is current')
                self.tick()
            if not self.stopped:mw.taskman.run_on_main(finish)
        threading.Thread(target=check,daemon=True).start()

    def mark_applied(self,version):
        if version>self.applied_revision:
            self.applied_revision=version
            self.config['applied_revision']=version
            mw.addonManager.writeConfig(NAME,self.config)
    def ack(self,identity):
        try:self.client().request('/v1/commands/'+self.config['device_id']+'/'+identity+'/ack','POST',{})
        except Exception:pass
    def defer_native_retry(self,manual=False):
        # Avoid hitting AnkiWeb every two seconds when offline or when a full
        # sync requires an explicit human direction choice.
        self.sync_attempt_failures=min(10,self.sync_attempt_failures+1)
        seconds=300 if manual else min(300,10 * (2 ** (self.sync_attempt_failures-1)))
        self.next_native_attempt_at=time.monotonic()+seconds

    def sync_then(self,after):
        if (self.syncing or self.native_collision_blocked or
                time.monotonic()<self.next_native_attempt_at):return
        auth=mw.pm.sync_auth()
        if not self.config.get('auto_sync',True) or not auth:
            print('Anki Companion: configure native Anki sync before automatic handoff')
            return
        self.syncing=True;self.last_sync=time.time()
        started_epoch=self.answers.sync_started()
        started_ticket=self.pending_ticket
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
                    self.defer_native_retry(manual=True)
                    self.native_sync_error='Initial/full sync requires a direction choice in Anki; study handoff deferred'
                    self.config['native_sync_error']=self.native_sync_error
                    mw.addonManager.writeConfig(NAME,self.config)
                    print('Anki Companion:',self.native_sync_error)
                    return
                self.sync_attempt_failures=0
                self.next_native_attempt_at=0
                if self.native_sync_error:
                    self.native_sync_error=''
                    self.config['native_sync_error']=''
                    mw.addonManager.writeConfig(NAME,self.config)
                self.collection_synced_ms=int(time.time()*1000)
                self.answers.sync_complete(started_epoch)
                # Never confirm a ticket generated after this sync started.
                if started_ticket and self.pending_ticket==started_ticket:
                    self.confirmed_ticket=started_ticket
                    self.pending_ticket=''
                    self.config['native_upload_ticket']=''
                    self.config['native_confirmed_ticket']=self.confirmed_ticket
                    mw.addonManager.writeConfig(NAME,self.config)
                mw.col._load_scheduler();mw.col.models._clear_cache()
                if mw.state in ('deckBrowser','overview'):
                    mw.reset()
                after();self.tick()
            except Exception as exc:
                self.defer_native_retry()
                self.native_sync_error='Native Anki sync failed; retry or resolve in Anki'
                self.config['native_sync_error']=self.native_sync_error
                mw.addonManager.writeConfig(NAME,self.config)
                print('Anki Companion native sync failed:',exc)
        # Anki owns the collection operation and scheduling merge; never copy its DB.
        try:
            # No blocking progress dialog while answering cards. Anki's own
            # task manager executes the native sync on a collection worker.
            mw.taskman.run_in_background(
                lambda:mw.col.sync_collection(auth,mw.pm.media_syncing_enabled()),
                finished,uses_collection=True)
        except Exception as exc:
            self.syncing=False;self.defer_native_retry()
            print('Anki Companion sync:',exc)
    def open_deck(self,identity):
        if self.stopped or not mw.col or not identity:return
        # Recompute after collection sync rather than opening a now-cleared deck.
        selected=next_deck(self.decks(),self.settings.get('parent_deck_id',''),self.settings.get('clearance','new_and_reviews'))
        if not selected:return
        identity=selected['id']
        mw.col.decks.select(int(identity));mw.moveToState('review')
    def undone(self,*args):
        # Anki's state_did_undo hook is emitted after its local undo commit.
        # Only a changed revlog creates a /retract; unrelated UI undos do not.
        self.undo_requested=True
        QTimer.singleShot(100,self.tick)

    def answered(self,*args):
        # The Anki review hook has committed an answer. Record the generation
        # NOW; a native sync in progress must not erase this pending work.
        self.answers.answer()
        QTimer.singleShot(100,self.after_answer)
    def after_answer(self):
        if self.stopped or not mw.col:return
        try:
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
def undone(*args):
    if controller:
        try:controller.undone(*args)
        except Exception as exc:print('Anki Companion undo callback:',exc)

def synced(*args):
    if controller:
        try:controller.collection_synced()
        except Exception as exc:print('Anki Companion sync callback:',exc)
# All GUI hooks are registered exactly once by the guarded __init__.py.
# Registering them again here would duplicate startup and review callbacks.
