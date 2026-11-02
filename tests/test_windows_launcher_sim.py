"""Isolated Windows 11/ASUS TUF A16 FA617NS profile & add-on startup simulation.

The hardware GPU/Windows installation is not available in CI; test the same
Anki2 layout, Qt hook ordering, and launcher-failure containment instead.
"""
import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from zipfile import ZipFile
from desktop import bootstrap

ROOT=Path(__file__).resolve().parents[1]


def _package(path):
    with ZipFile(path,'w') as archive:
        for name in ('__init__.py','bridge.py','history.py','rules.py','transport.py',
                     'review_epoch.py','config.json','config.md','manifest.json'):
            data=(ROOT/'anki_addon'/name).read_bytes()
            archive.writestr(name,data)


def test_windows_11_profile_simulator_preserves_real_anonymous_anki_data(tmp_path,monkeypatch):
    roaming=tmp_path/'Users'/'Owner'/'AppData'/'Roaming'
    root=roaming/'Anki2'
    home=root/'User 1'; home.mkdir(parents=True)
    local=tmp_path/'Users'/'Owner'/'AppData'/'Local'
    (local/'AnkiCompanion'/'server').mkdir(parents=True)
    (local/'AnkiCompanion'/'server'/'token.txt').write_text('my-simulation-token-123456789')
    collection=home/'collection.anki2'
    collection.write_bytes(b'Private user collection must be untouched')
    (home/'collection.media').mkdir()
    (home/'collection.media'/'image.jpg').write_bytes(b'picture')
    other=root/'addons21'/'other_plugin';other.mkdir(parents=True)
    (other/'__init__.py').write_text('existing addon')
    monkeypatch.setenv('APPDATA',str(roaming))
    monkeypatch.setenv('LOCALAPPDATA',str(local))
    archive=tmp_path/'bridge.ankiaddon';_package(archive)
    monkeypatch.setattr(bootstrap,'addon_archive',lambda:archive)
    assert 'installed' in bootstrap.ensure_anki_bridge()
    assert collection.read_bytes()==b'Private user collection must be untouched'
    assert (home/'collection.media'/'image.jpg').read_bytes()==b'picture'
    assert (other/'__init__.py').read_text()=='existing addon'
    assert (root/'addons21'/'anki_companion_bridge'/'__init__.py').read_bytes()==(ROOT/'anki_addon'/'__init__.py').read_bytes()
    assert 'installed' in bootstrap.ensure_anki_bridge()


def test_anki_profile_did_open_and_answer_hooks_survive_all_integration_exceptions(monkeypatch):
    calls=[]
    hooks=types.SimpleNamespace(**{k:[] for k in (
        'profile_did_open','profile_will_close','reviewer_did_answer_card',
        'state_did_undo','sync_did_finish')})
    fake_aqt=types.ModuleType('aqt')
    fake_aqt.gui_hooks=hooks
    monkeypatch.setitem(sys.modules,'aqt',fake_aqt)
    package=ROOT/'anki_addon'
    spec=importlib.util.spec_from_file_location('anki_companion_bridge',(package/'__init__.py'),
                                               submodule_search_locations=[str(package)])
    instance=importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules,'anki_companion_bridge',instance)
    # A failing optional bridge can never crash the actual native Anki launcher.
    failing=types.ModuleType('anki_companion_bridge.bridge')
    def failed(*args):raise RuntimeError('Native Anki sync unavailable')
    failing.opened=failing.closed=failing.answered=failing.undone=failing.synced=failed
    monkeypatch.setitem(sys.modules,'anki_companion_bridge.bridge',failing)
    spec.loader.exec_module(instance)
    assert all(len(getattr(hooks,k))==1 for k in vars(hooks))
    hooks.profile_did_open[0]()
    hooks.reviewer_did_answer_card[0](object(),object(),3)
    hooks.state_did_undo[0](object())
    hooks.sync_did_finish[0]()
    hooks.profile_will_close[0]()


def test_windows_launcher_isolation_handles_missing_optional_aqt_api(monkeypatch):
    fake=types.ModuleType('aqt')
    fake.gui_hooks=types.SimpleNamespace(profile_did_open=[])
    monkeypatch.setitem(sys.modules,'aqt',fake)
    package=ROOT/'anki_addon'
    spec=importlib.util.spec_from_file_location('anki_companion_bridge_isolation',package/'__init__.py',
                                               submodule_search_locations=[str(package)])
    instance=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(instance)
    assert len(fake.gui_hooks.profile_did_open)==1
    fake.gui_hooks.profile_did_open[0]()

def test_windows_real_aqt_smoke_disables_only_invisible_first_run_lang_modal():
    from pathlib import Path
    script=(Path(__file__).resolve().parents[1]/'scripts/ci_windows_anki_launcher.py').read_text()
    assert 'ProfileManager.setDefaultLang = choose_ci_language' in script
    assert 'manager.setLang("en")' in script
    assert "app=aqt._run(" in script
    assert 'faulthandler.dump_traceback_later' in script


def test_real_anki_ci_smoke_does_not_fail_after_gui_success_due_to_locked_temp_log():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/'scripts/ci_windows_anki_launcher.py').read_text()
    assert "ignore_cleanup_errors=True" in source
    assert "PASS: real Anki/AQt opened" in source


def test_real_anki_gui_smoke_verifies_review_hook_and_exits_before_qt_atexit():
    source=(ROOT/'scripts/ci_windows_anki_launcher.py').read_text()
    assert 'gui_hooks.reviewer_did_answer_card' in source
    assert "windows-anki-gui.json" in source
    assert 'os._exit(0)' in source
    assert source.index("assert (addon_dir/'__init__.py').is_file()") < source.index('os._exit(0)')
    assert source.index('review_hook_registered') < source.index('os._exit(0)')


def test_real_anki_hook_is_noniterable_generated_object():
    """Match upstream Anki 26.09's generated hook API, not a Python list."""
    class ActualStyleHook:
        _hooks=[]
        def count(self):return len(self._hooks)
        def append(self,fn):self._hooks.append(fn)
        # no __iter__; 'for fn in hook' must crash, as CI demonstrated.
    hook=ActualStyleHook()
    assert not hook.count()
    def observer(): pass
    observer.__module__='anki_companion_bridge'
    hook.append(observer)
    assert hook.count() and any(
        getattr(fn,'__module__','').endswith('anki_companion_bridge')
        for fn in hook._hooks)
    source=(ROOT/'scripts/ci_windows_anki_launcher.py').read_text()
    assert "getattr(review_hook, '_hooks', ())" in source
    assert 'review_hook.count() > 0' in source
    assert 'for fn in gui_hooks.reviewer_did_answer_card' not in source


def test_windows_aniki_smoke_supports_gui_error_handler_without_flush():
    """Anki 26.09 wraps sys.stderr with a non-file ErrorHandler."""
    class ErrorHandler:
        def write(self, text):pass
    class Stream:
        def flush(self):pass
    streams=(Stream(),ErrorHandler())
    for stream in streams:
        callback=getattr(stream,'flush',None)
        if callable(callback):callback()
    text=(ROOT/'scripts/ci_windows_anki_launcher.py').read_text()
    assert "getattr(stream, 'flush', None)" in text
    assert 'sys.stderr.flush()' not in text
    assert 'os._exit(0)' in text
