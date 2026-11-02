from zipfile import ZipFile
import json
import types
import sys
import importlib.util
from desktop import bootstrap


def pack(path,version='v1',with_bad_path=False):
    files={name:b'x' for name in ['__init__.py','bridge.py','history.py','rules.py','transport.py','config.json','config.md']}
    files['manifest.json']=b'{"package":"anki_companion_bridge"}'
    files['bridge.py']=version.encode()
    with ZipFile(path,'w') as archive:
        for key,value in files.items():archive.writestr(key,value)
        if with_bad_path:archive.writestr('../outside',b'no')

def test_desktop_auto_installs_upgrade_preserving_profile_metadata(tmp_path,monkeypatch):
    home=tmp_path/'Roaming';(home/'Anki2').mkdir(parents=True)
    monkeypatch.setenv('APPDATA',str(home))
    installer=tmp_path/'bridge.ankiaddon';pack(installer)
    monkeypatch.setattr(bootstrap,'addon_archive',lambda:installer)
    assert 'installed' in bootstrap.ensure_anki_bridge()
    path=home/'Anki2'/'addons21'/'anki_companion_bridge'
    assert (path/'bridge.py').read_text()=='v1'
    (path/'meta.json').write_text('{"config":{"keep":"my-preferences"}}')
    pack(installer,'v2');assert 'installed' in bootstrap.ensure_anki_bridge()
    assert (path/'bridge.py').read_text()=='v2'
    assert json.loads((path/'meta.json').read_text())['config']['keep']=='my-preferences'
    assert bootstrap.ensure_anki_bridge()=='Anki desktop bridge installed'

def test_rejects_untrusted_paths_without_touching_collection(tmp_path,monkeypatch):
    home=tmp_path/'Roaming';(home/'Anki2').mkdir(parents=True)
    monkeypatch.setenv('APPDATA',str(home))
    installer=tmp_path/'bridge.ankiaddon';pack(installer,with_bad_path=True)
    monkeypatch.setattr(bootstrap,'addon_archive',lambda:installer)
    import pytest
    with pytest.raises(ValueError,match='validation'):
        bootstrap.ensure_anki_bridge()
    assert not (tmp_path/'outside').exists()

def test_anonymous_addon_import_never_crashes_even_when_aqt_is_absent(tmp_path,monkeypatch):
    from importlib.machinery import SourceFileLoader
    import importlib.util
    source=__import__('pathlib').Path(__file__).resolve().parents[1]/'anki_addon'/'__init__.py'
    spec=importlib.util.spec_from_loader('broken_test_addon',SourceFileLoader('broken_test_addon',str(source)))
    addon=importlib.util.module_from_spec(spec)
    # This must not throw even outside Anki or when an optional AQT hook changes.
    spec.loader.exec_module(addon)
    addon._start()  # Failure is isolated, not propagated to Anki.
