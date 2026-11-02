"""Real Anki/AQt launch smoke on a Windows x64 CI runner; NEVER user's profile.

Uses Anki 26.9.3 Python AQt in an isolated -b profile, Qt offscreen and
software rendering to cover the user's disabled Radeon/Code-22 fallback.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import os, sys, traceback
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))


def smoke():
    if sys.platform!='win32':
        raise RuntimeError('This test needs the actual Windows x64 CI runner')
    import aqt
    from desktop import bootstrap
    import subprocess
    with TemporaryDirectory(prefix='anki-companion-win11-') as tmp:
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
        app=aqt._run(['anki','-b',str(roaming/'Anki2'),'-l','en'],exec=False)
        if app is None or aqt.mw is None:
            raise RuntimeError('Anki launcher did not create its GUI window')
        assert getattr(aqt.mw,'addonManager',None) is not None
        print('PASS: real Anki/AQt opened on isolated Windows x64 profile with companion bridge')
        app.quit()

if __name__=='__main__':
    try:smoke()
    except BaseException:
        traceback.print_exc();sys.exit(1)
