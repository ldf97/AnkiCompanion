"""FCM wake-path acceptance without a Google credential or live phone.

Tests verify persistent registrations, scoped idempotent dispatch, and
that no network call is on the review endpoint's response path.
"""
import threading
from time import monotonic, sleep
from fastapi.testclient import TestClient
from server.main import create_app

TOKEN='integration-token-1234567890'
NOW=1793700000000


def client(root, send=None):
    return TestClient(create_app(root,TOKEN,lambda:NOW,fcm_send=send),
                      headers={'Authorization':'Bearer '+TOKEN})


def registration(device, collection='primary', token=None):
    return {'device_id':device,'collection_id':collection,
            'fcm_token':token or (device+'-')*20}


def post_event(c,device,card,collection='primary'):
    return c.post('/v1/events',json={'device_id':device,'events':[
        {'collection_id':collection,'revlog_id':NOW-60000+card,
         'card_id':card,'duration_ms':2000}]})


def await_messages(messages,n):
    limit=monotonic()+3
    while len(messages)<n and monotonic()<limit:sleep(.02)
    assert len(messages)>=n, messages


def test_push_registration_is_persistent_and_authenticated(tmp_path):
    c=client(tmp_path)
    assert c.post('/v1/push/register',json=registration('phone'),
                  headers={'Authorization':'Bearer wrong'}).status_code==401
    assert c.post('/v1/push/register',json=registration('phone')).json()=={
        'ok':True,'configured':False}
    assert c.get('/v1/push/status').json()['registered_devices']==1
    assert client(tmp_path).get('/v1/push/status').json()['registered_devices']==1
    assert c.post('/v1/push/register',json=registration('phone',token='new'+'x'*35)).status_code==200
    assert c.get('/v1/push/status').json()['registered_devices']==1
    assert c.post('/v1/push/register',json=registration('!',token='x'*60)).status_code==422
    assert c.post('/v1/push/test',json={'device_id':'phone'}).status_code==503


def test_review_wakes_other_device_only_and_not_on_duplicate(tmp_path):
    messages=[]; entered=threading.Event(); release=threading.Event()
    def send(token,collection,sequence):
        messages.append((token,collection,sequence))
        entered.set()
        release.wait(2)
    c=client(tmp_path,send=send)
    for d in ['pc1','phone','pc2']:
        assert c.post('/v1/push/register',json=registration(d)).status_code==200
    assert post_event(c,'pc1',5).json()['inserted']==1
    assert entered.wait(2)
    # This POST completed even while the FCM backend is deliberately stalled.
    release.set();await_messages(messages,2)
    assert {r[0] for r in messages}=={registration('phone')['fcm_token'],registration('pc2')['fcm_token']}
    assert all(r[1]=='primary' and r[2]>0 for r in messages)
    assert post_event(c,'pc1',5).json()['inserted']==0
    sleep(.05)
    assert len(messages)==2


def test_collection_and_target_scoping(tmp_path):
    messages=[]
    c=client(tmp_path,send=lambda token,collection,sequence:messages.append((token,collection,sequence)))
    for device,collection in [('origin','alpha'),('phone','alpha'),('other','beta')]:
        c.post('/v1/push/register',json=registration(device,collection))
    assert post_event(c,'origin',12,'alpha').status_code==200
    await_messages(messages,1)
    assert len(messages)==1 and messages[0][0]==registration('phone','alpha')['fcm_token']
    assert c.post('/v1/push/test',json={'device_id':'phone'}).json()=={'queued':True,'delivered':False}
    await_messages(messages,2)
    assert messages[1][2]==0


def test_missing_credentials_does_not_block_reviews(tmp_path):
    c=client(tmp_path)
    c.post('/v1/push/register',json=registration('phone'))
    assert c.get('/v1/push/status').json()['configured'] is False
    assert post_event(c,'pc1',2).status_code==200
    assert c.get('/v1/state').json()['progress']['answers']==1