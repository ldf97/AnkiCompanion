"""Two independent HTTP clients over real TLS; no simulated TestClient transport."""
from datetime import datetime, timedelta, timezone
import ipaddress, os, secrets, socket, ssl, subprocess, sys, time
import httpx, pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

def test_tls_authentication_and_cross_client_progress(tmp_path):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')]);now=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
          .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),False)
          .sign(key,hashes.SHA256()))
    cert_path=tmp_path/'fixture.pem';key_path=tmp_path/'fixture.key'
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    token=secrets.token_urlsafe(32)
    env=dict(os.environ,ANKI_COMPANION_DATA=str(tmp_path/'server'),ANKI_COMPANION_TOKEN=token)
    command=[sys.executable,'-m','uvicorn','server.main:create_app','--factory','--host','127.0.0.1','--port',str(port),'--ssl-keyfile',str(key_path),'--ssl-certfile',str(cert_path)]
    with (tmp_path/'https.log').open('w') as log:
        process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        context=ssl.create_default_context(cafile=str(cert_path));url=f'https://127.0.0.1:{port}'
        try:
            with httpx.Client(base_url=url,verify=context,trust_env=False) as desktop,httpx.Client(base_url=url,verify=context,trust_env=False) as phone:
                for _ in range(100):
                    try:
                        if desktop.get('/health').status_code==200:break
                    except httpx.ConnectError:time.sleep(.1)
                assert desktop.get('/v1/state').status_code==401
                with pytest.raises(httpx.ConnectError):httpx.get(url+'/health',trust_env=False)
                desktop.headers['Authorization']='Bearer '+token;phone.headers['Authorization']='Bearer '+token
                settings=desktop.get('/v1/settings').json();settings.update(lesson_answers=50,lesson_ms=0)
                assert desktop.put('/v1/settings',json=settings).status_code==200
                def send(client,start,count):
                    stamp=int(time.time()*1000)-60000
                    return client.post('/v1/events',json={'events':[dict(collection_id='primary',revlog_id=stamp+i,card_id=i+1,duration_ms=1000) for i in range(start,start+count)]})
                assert send(desktop,0,20).status_code==200
                assert phone.get('/v1/state').json()['progress']['answers']==20
                assert send(phone,20,10).status_code==200
                state=desktop.get('/v1/state').json();assert state['progress']['answers']==30
                assert state['progress']['percent']==60 and state['progress']['remaining']==20
                assert send(desktop,30,20).status_code==200
                assert phone.get('/v1/state').json()['completed']
                print('PASS: authenticated HTTPS, untrusted certificate rejected, independent clients see 20/30/50. Local loopback only, not physical network verification.')
        finally:process.terminate();process.wait(timeout=15)
