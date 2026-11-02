"""Real Anki/AQt launch smoke on a Windows x64 CI runner; NEVER user's profile.

Uses Anki 26.9.3 Python AQt in an isolated -b profile, Qt offscreen and
software rendering to cover the user's disabled Radeon/Code-22 fallback.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import os, sys, traceback, faulthandler
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))


def smoke():
    if sys.platform!='win32':
        raise RuntimeError('This test needs the actual Windows x64 CI runner')
    import aqt
    from desktop import bootstrap
    import subprocess
    # Anki keeps crash.log open briefly after app.quit() on Windows; the GUI
    # launch passed, so a temporary log lock must not fail acceptance.
    with TemporaryDirectory(prefix='anki-companion-win11-', ignore_cleanup_errors=True) as tmp:
        home=Path(tmp)
        roaming=home/'Roaming';local=home/'Local'
        (roaming/'Anki2').mkdir(parents=True)
        local.mkdir()
        os.environ['APPDATA']=str(roaming)
        os.environ['LOCALAPPDATA']=str(local)
        os.environ['QT_QPA_PLATFORM']='offscreen'
        os.environ['QT_OPENGL']='software'
        os.environ['QSG_RHI_BACKEND']='software'
        os.environ['QTWEBENGINE_DISABLE_SANDBOX']='1'
        # Tests the packaged real add-on and the actual bundled installer path.
        subprocess.run([sys.executable, 'scripts/package_addon.py'],check=True)
        archive=Path('packages/Anki_Companion_Bridge.ankiaddon')
        if not Path(archive).is_file():
            raise RuntimeError('Anki bridge packaging did not produce an archive')
        assert 'installed' in bootstrap.ensure_anki_bridge()
        # Anki supports -b alternate profile path, per the official manual.
        # exec=False returns after window setup, proving addon import and
        # startup instead of timing out a GUI indefinitely.
        # CI uses a noninteractive Windows service session. If Anki opens a
        # hidden modal/first-run window, dump the Python stacks and fail
        # decisively rather than burning the entire 12-minute Windows job.
        faulthandler.enable()
        faulthandler.dump_traceback_later(75, repeat=False, exit=True)
        # The upstream Anki 26.09.3 first-run language selector is a
        # QDialog.exec() modal. It is invisible under Qt offscreen rendering
        # and cannot be dismissed by a Windows CI agent. Seed English in this
        # disposable test profile; do NOT modify installed Anki or user files.
        from aqt.profiles import ProfileManager
        def choose_ci_language(manager, index):
            manager.setLang("en")
        ProfileManager.setDefaultLang = choose_ci_language
        print("Starting isolated Anki GUI with companion bridge",flush=True)
        app=aqt._run(['anki','-b',str(roaming/'Anki2'),'-l','en'],exec=False)
        if app is None or aqt.mw is None:
            raise RuntimeError('Anki launcher did not create its GUI window')
        assert getattr(aqt.mw,'addonManager',None) is not None
        print('PASS: real Anki/AQt opened on isolated Windows x64 profile with companion bridge')
        faulthandler.cancel_dump_traceback_later()
        app.quit()

if __name__=='__main__':
    try:smoke()
    except BaseException:
        traceback.print_exc();sys.exit(1)
