from pathlib import Path
from tempfile import TemporaryDirectory, NamedTemporaryFile
from functools import lru_cache
import secrets, os, time, threading, json, sys
from fastapi import FastAPI, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from companion.packs import Packs
from companion.rules import scene, next_deck
from app.widget_engine import WidgetEngine
from app.skin_packs import PackError
from .store import Store, Conflict
from .models import Events, Retractions, Snapshot, Settings, Command
from .updates import ReleaseFeed,UpdateError
from .fcm import FcmDispatcher

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share')))/'AnkiCompanion/server' if getattr(sys,'frozen',False) else ROOT/'data'

class PushRegistration(BaseModel):
    device_id: str = Field(min_length=1,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    collection_id: str = Field(default='primary',min_length=1,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    fcm_token: str = Field(min_length=32,max_length=4096,pattern=r'^\S+$')

class PushTest(BaseModel):
    device_id: str = Field(min_length=1,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')


def create_app(data_dir=None, token=None, clock=None, fcm_send=None):
    data = Path(data_dir or os.environ.get('ANKI_COMPANION_DATA', DEFAULT_DATA))
    data.mkdir(parents=True, exist_ok=True)
    token_file = data/'token.txt'
    if token is None:
        token = os.environ.get('ANKI_COMPANION_TOKEN')
        if not token:
            if not token_file.exists():
                # Existing study history must NEVER be paired to a brand-new
                # token silently after a partial restore or failed upgrade.
                if (data/'companion.sqlite3').exists():
                    raise RuntimeError('Existing server database has no pairing token; restore token.txt from the verified backup before starting')
                token_file.write_text(secrets.token_urlsafe(32)); token_file.chmod(0o600)
            token = token_file.read_text().strip()
    if len(token) < 16: raise ValueError('Server token must contain at least 16 characters')
    now = clock or (lambda: int(time.time()*1000))
    store = Store(data/'companion.sqlite3'); packs = Packs(ROOT/'skins', data/'packs')
    render_lock = threading.Lock()
    feed=ReleaseFeed(data/'updates')
    api = FastAPI(title='Anki Companion', version='0.1.0', docs_url=None, redoc_url=None, openapi_url=None)
    api.state.store = store; api.state.packs = packs
    api.state.feed=feed
    push=FcmDispatcher(store,data,send=fcm_send)
    api.state.fcm=push

    def publish_mutation(sequence_before):
        # Send only committed, durable changes, never on card-answer UI path.
        push.publish(store.new_push_changes(sequence_before))

    def auth(authorization: str = Header(default='')):
        if not secrets.compare_digest(authorization, 'Bearer ' + token):
            raise HTTPException(401, 'Authentication required')

    @api.exception_handler(Conflict)
    async def conflict(request, exc):
        return Response(json.dumps({'detail':str(exc)}), status_code=409, media_type='application/json')

    @api.exception_handler(PackError)
    async def pack_error(request, exc):
        return Response(json.dumps({'detail':str(exc)}), status_code=400, media_type='application/json')

    @api.get('/health')
    def health(): return {'status':'ok'}

    @api.get('/v1/push/status', dependencies=[Depends(auth)])
    def push_status(): return push.status()

    @api.post('/v1/push/reload', dependencies=[Depends(auth)])
    def push_reload(): return push.reload()

    @api.post('/v1/push/register', dependencies=[Depends(auth)])
    def push_register(registration:PushRegistration):
        store.register_push(registration.device_id,registration.collection_id,
                            registration.fcm_token)
        return {'ok':True, 'configured':push.configured}

    @api.post('/v1/push/test', dependencies=[Depends(auth)])
    def push_test(request:PushTest):
        if not push.configured:
            raise HTTPException(503,'FCM service account has not been configured on Windows')
        if not push.test(request.device_id):
            raise HTTPException(404,'That Android device has not registered an FCM token')
        return {'queued':True,'delivered':False}

    @api.get('/v1/updates/{platform}',dependencies=[Depends(auth)])
    def updates(platform:str,current:str='0.0.0',build:int=0,force:bool=False):
        if platform not in ('android','windows','source'):raise HTTPException(404,'Unknown platform')
        repository=os.environ.get('ANKI_COMPANION_REPOSITORY') or store.settings().get('update_repository','')
        try:return feed.check(repository,platform,current,build,force)
        except Exception as exc:raise HTTPException(502,'Release check failed: '+str(exc)) from exc

    @api.get('/v1/updates/download/{identity}',dependencies=[Depends(auth)])
    def download_update(identity:str):
        repository=os.environ.get('ANKI_COMPANION_REPOSITORY') or store.settings().get('update_repository','')
        try:path,name=feed.download(repository,identity)
        except Exception as exc:raise HTTPException(502,'Update download failed: '+str(exc)) from exc
        return FileResponse(path,filename=name,media_type='application/octet-stream')

    @api.get('/v1/changes', dependencies=[Depends(auth)])
    def changes(since: int = 0, wait_ms: int = 0, device_id: str = '', collection_id: str = ''):
        # Device-specific durable long-poll; never echo a review to its source.
        # This is a dispatch wakeup, NOT proof native Anki/AnkiWeb sync finished.
        if (since < 0 or not 0 <= wait_ms <= 4000 or
                len(device_id) > 100 or len(collection_id) > 100 or
                (collection_id and not __import__('re').fullmatch(r'[A-Za-z0-9_-]+',collection_id))):
            raise HTTPException(400, 'Invalid change cursor, scope or wait')
        deadline = time.monotonic() + wait_ms / 1000.0
        while True:
            change = store.changes_since(since,device_id,collection_id)
            if (change['sequence'] != since or change['reset'] or
                    time.monotonic() >= deadline):
                return change
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))

    @api.get('/v1/state', dependencies=[Depends(auth)])
    def state(device_id: str = '', collection_id: str = 'primary'):
        value = store.state(packs, now())
        skin, _ = packs.get(value['lineup']['skin_id'], value['lineup']['skin_version'])
        value['scene'] = scene(skin, value['lineup'], now(), value['settings'], value['completed'], value['streak'])
        value['next_decks'] = {d['device_id']: next_deck(d['decks'], value['settings']['parent_deck_id'], value['settings']['clearance']) for d in value['devices']}
        value['native_sync'] = store.sync_status(device_id, collection_id)
        return value

    @api.put('/v1/settings', dependencies=[Depends(auth)])
    def settings(body: Settings):
        packs.get(body.skin_id, body.skin_version)
        before=store.change_sequence()
        result=store.update_settings(body.model_dump(), packs=packs, now_ms=now())
        publish_mutation(before)
        return result

    @api.get('/v1/settings', dependencies=[Depends(auth)])
    def read_settings(): return store.settings()

    @api.post('/v1/events', dependencies=[Depends(auth)])
    def events(body: Events):
        try:
            before=store.change_sequence()
            result=store.add_events(body.events, packs, now(),body.device_id)
            publish_mutation(before)
            return result
        except Conflict: raise
        except ValueError as exc: raise HTTPException(400,str(exc)) from exc

    @api.get('/v1/events/audit', dependencies=[Depends(auth)])
    def event_audit(after:str='',limit:int=100):
        try: return store.audit_events(after,limit)
        except ValueError as exc: raise HTTPException(400,str(exc)) from exc

    @api.post('/v1/events/retract', dependencies=[Depends(auth)])
    def retract(body: Retractions):
        try:
            before=store.change_sequence()
            store.retract(body.ids,body.device_id,now())
            publish_mutation(before)
        except ValueError as exc: raise HTTPException(400,str(exc)) from exc
        return {'ok':True}

    @api.post('/v1/snapshots', dependencies=[Depends(auth)])
    def snapshot(body: Snapshot):
        before=store.change_sequence()
        store.snapshot(body,now())
        publish_mutation(before)
        return {'ok':True}

    @api.post('/v1/commands', dependencies=[Depends(auth)])
    def command(body: Command):
        before=store.change_sequence()
        identity=store.enqueue(body,now())
        publish_mutation(before)
        return {'id':identity}

    @api.get('/v1/commands/{device}', dependencies=[Depends(auth)])
    def commands(device: str): return {'commands':store.commands(device,now())}

    @api.post('/v1/commands/{device}/{identity}/ack', dependencies=[Depends(auth)])
    def ack(device:str, identity:str):
        store.ack(identity,device); return {'ok':True}

    @api.get('/v1/skins', dependencies=[Depends(auth)])
    def skins():
        return {'skins':[{'id':s['id'],'version':s['version'],'name':s['name']} for s,p in packs.list().values()]}

    @api.get('/v1/skins/{identity}/{version}/manifest', dependencies=[Depends(auth)])
    def manifest(identity:str,version:str): return packs.get(identity,version)[0]

    @api.get('/v1/skins/{identity}/{version}/pack.zip', dependencies=[Depends(auth)])
    def download(identity:str,version:str):
        packs.get(identity,version)
        dest=data/'exports'/f'{identity}-{version}.zip';dest.parent.mkdir(exist_ok=True)
        with render_lock:
            if not dest.exists():
                temp=dest.with_suffix('.tmp');packs.export(identity,version,temp);temp.replace(dest)
        return FileResponse(dest,media_type='application/zip')

    @api.post('/v1/skins/import', dependencies=[Depends(auth)])
    async def install(request:Request):
        with NamedTemporaryFile(suffix='.zip',dir=data,delete=False) as temp:
            path=Path(temp.name); size=0
            try:
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>50*1024*1024: raise HTTPException(413,'Skin ZIP exceeds 50 MiB')
                    temp.write(chunk)
                temp.flush()
                temp.close()
                with render_lock: result=packs.install(path)
                before=store.change_sequence()
                store.notify_catalog_change()
                publish_mutation(before)
                return {'id':result['id'],'version':result['version'],'name':result['name']}
            finally:
                temp.close()
                path.unlink(missing_ok=True)

    @lru_cache(maxsize=12)
    def render_cached(serialized, identity, version):
        _, root=packs.get(identity,version)
        with render_lock,TemporaryDirectory(dir=data) as temp:
            renderer=WidgetEngine(root,temp)
            return renderer.render(json.loads(serialized),temp).read_bytes()

    @api.get('/v1/frame.png', dependencies=[Depends(auth)])
    def frame():
        value=state();lineup=value['lineup']
        payload=render_cached(json.dumps(value['scene'],sort_keys=True),lineup['skin_id'],lineup['skin_version'])
        return Response(payload,media_type='image/png',headers={'Cache-Control':'private, no-store'})

    return api

def main():
    import argparse,uvicorn
    parser=argparse.ArgumentParser(description='Personal Anki Companion server')
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8766' if sys.platform == 'win32' else '8765')))
    parser.add_argument('--data',default=str(DEFAULT_DATA));args=parser.parse_args()
    app=create_app(args.data)
    print('Pairing token is stored in',Path(args.data).resolve()/'token.txt')
    uvicorn.run(app,host=args.host,port=args.port)

if __name__=='__main__': main()