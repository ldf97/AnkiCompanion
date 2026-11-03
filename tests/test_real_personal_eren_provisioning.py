"""Opt-in personal acceptance; private artwork is NEVER committed publicly.

Run with ANKI_COMPANION_ORIGINAL_EREN_ZIP=<owner's verified original pack>.
This test uses the actual private file, fake Windows install layout, server
endpoints, and one-time default selection; it does not alter Anki profiles.
"""
import io
import hashlib
import json
import os
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from fastapi.testclient import TestClient

from desktop import bootstrap
from server.main import create_app


@pytest.mark.skipif(not os.environ.get('ANKI_COMPANION_ORIGINAL_EREN_ZIP'),
                    reason='Original private artwork is not included in public source')
def test_owner_installer_auto_selects_real_eren_and_retains_skin_upload(tmp_path,monkeypatch):
    original=Path(os.environ['ANKI_COMPANION_ORIGINAL_EREN_ZIP']).read_bytes()
    assert hashlib.sha256(original).hexdigest()==bootstrap.EREN_SHA256
    with ZipFile(io.BytesIO(original)) as z:
        originals={x.filename:hashlib.sha256(z.read(x.filename)).hexdigest() for x in z.infolist() if not x.is_dir()}
    assert len(originals)==30, 'Do not lose any original image, quote manifest, or icon assets'
    installed=tmp_path/'Program Files'/'AnkiCompanion'
    desktop_exe=installed/'desktop'/'AnkiCompanion.exe'
    desktop_exe.parent.mkdir(parents=True)
    desktop_exe.write_bytes(b'executable placeholder -- installer filesystem test')
    personal_skin=installed/'skins'/'Eren-Anki-Private-Skin-1.0.0.zip'
    personal_skin.parent.mkdir(parents=True)
    personal_skin.write_bytes(original)
    monkeypatch.setattr(bootstrap.sys,'executable',str(desktop_exe))
    monkeypatch.setattr(bootstrap.sys,'frozen',True,raising=False)
    server_root=tmp_path/'LocalAppData'/'AnkiCompanion'/'server'
    monkeypatch.setattr(bootstrap,'data_dir',lambda:server_root)

    app=create_app(data_dir=server_root)
    token=(server_root/'token.txt').read_text()
    with TestClient(app,headers={'Authorization':'Bearer '+token}) as http:
        class ClientAdapter:
            def request(self,path,method='GET',data=None,content_type=None,**kwargs):
                if method=='POST' and content_type=='application/zip':
                    r=http.post(path,content=data,headers={'Content-Type':'application/zip'})
                elif method=='PUT': r=http.put(path,json=data)
                else: r=http.get(path)
                assert r.status_code==200,(path,r.status_code,r.text[:300])
                return r.json()
        client=ClientAdapter()
        assert bootstrap.find_original_eren()==original
        assert bootstrap.recover_eren(client)=='Eren artwork activated by default'
        state=http.get('/v1/state').json()
        assert state['settings']['skin_id']=='eren_anki'
        assert state['lineup']['skin_id']=='eren_anki'
        assert http.get('/v1/frame.png').status_code==200
        downloaded=http.get('/v1/skins/eren_anki/1.0.0/pack.zip')
        assert downloaded.status_code==200
        with ZipFile(io.BytesIO(downloaded.content)) as shipped:
            hashes={name:hashlib.sha256(shipped.read(name)).hexdigest() for name in shipped.namelist() if not name.endswith('/')}
        assert hashes==originals

        # Upload an independent skin: the feature must still work and must not
        # mutate/delete the original Eren pack or its frozen daily history.
        manifest=json.loads((Path(__file__).resolve().parents[1]/'skins/study_companion/skin.json').read_text())
        manifest.update(id='custom_uploaded_skin',name='My new uploaded skin')
        skinbase=Path(__file__).resolve().parents[1]/'skins/study_companion'
        buffer=io.BytesIO()
        with ZipFile(buffer,'w',ZIP_DEFLATED) as output:
            for path in skinbase.rglob('*'):
                if path.is_file():
                    name=path.relative_to(skinbase).as_posix()
                    data=json.dumps(manifest).encode() if name=='skin.json' else path.read_bytes()
                    output.writestr(name,data)
        response=http.post('/v1/skins/import',content=buffer.getvalue(),headers={'Content-Type':'application/zip'})
        assert response.status_code==200,response.text
        settings=http.get('/v1/settings').json()
        settings.update(skin_id='custom_uploaded_skin',skin_version='1.0.0')
        assert http.put('/v1/settings',json=settings).status_code==200
        assert 'selected skin preserved' in bootstrap.recover_eren(client)
        assert http.get('/v1/settings').json()['skin_id']=='custom_uploaded_skin'
        assert (server_root/'packs'/'eren_anki'/'1.0.0'/'skin.json').exists()
        assert len(list((server_root/'packs'/'eren_anki'/'1.0.0').rglob('*')))>=30

    # App/server restart must never reset custom selection or erase images.
    restarted=create_app(data_dir=server_root)
    with TestClient(restarted,headers={'Authorization':'Bearer '+token}) as http:
        assert http.get('/v1/settings').json()['skin_id']=='custom_uploaded_skin'
        assert {'eren_anki','custom_uploaded_skin'}.issubset({x['id'] for x in http.get('/v1/skins').json()['skins']})
