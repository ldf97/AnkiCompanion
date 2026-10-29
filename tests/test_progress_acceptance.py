"""Server component acceptance, deliberately not a two-device Anki sync test."""
from tests.test_server import TOKEN,NOW,event
from server.main import create_app
from fastapi.testclient import TestClient

def test_20_desktop_10_phone_20_desktop_with_retries_undo_and_rollover(tmp_path):
    clock=[NOW];app=create_app(tmp_path,TOKEN,lambda:clock[0])
    c=TestClient(app,headers={'Authorization':'Bearer '+TOKEN})
    settings=c.get('/v1/settings').json()
    assert c.put('/v1/settings',json=dict(settings,lesson_answers=50,lesson_ms=0)).status_code==200
    cards=[event(i,1000,i+1) for i in range(51)]
    def send(rows,device):
        r=c.post('/v1/events',json={'events':rows,'device_id':device});assert r.status_code==200
    def check(answers,percent,remaining,done):
        s=c.get('/v1/state').json();p=s['progress']
        assert (p['answers'],p['percent'],p['remaining'],s['completed'])==(answers,percent,remaining,done)
    send(cards[:20],'desktop');check(20,40,30,False)
    send(cards[20:30],'phone');check(30,60,20,False)
    send(cards[:30],'desktop');send(cards[:30][::-1],'phone');check(30,60,20,False)
    first=cards[0];key=f"primary:{first['revlog_id']}:{first['card_id']}"
    assert c.post('/v1/events/retract',json={'ids':[key]}).status_code==200
    check(29,58,21,False)
    send(cards[30:50][::-1],'desktop');check(49,98,1,False)
    send([cards[50]],'phone');check(50,100,0,True)
    clock[0]+=86400000
    check(0,0,50,False)
    assert c.get('/v1/state').json()['streak']==1
