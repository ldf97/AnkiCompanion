"""Smoke-test the REAL Inno-installed Windows GUI after an in-place update.

Runs only on the disposable GitHub Windows runner, never the owner's profile.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def smoke(localappdata=None, *, hold_seconds=8):
    if sys.platform != 'win32':
        raise RuntimeError('Installed Windows GUI smoke requires a real Windows runner')
    home=Path(localappdata or os.environ['LOCALAPPDATA'])
    executable=home/'Programs'/'AnkiCompanion'/'desktop'/'AnkiCompanion.exe'
    if not executable.is_file():
        raise FileNotFoundError(f'Installed Windows companion binary is missing: {executable}')
    output=Path('test-results')
    output.mkdir(exist_ok=True)
    log=output/'windows-installed-app.log'
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_OPENGL='software',
             QSG_RHI_BACKEND='software',ANKI_COMPANION_SKIN='study_companion')
    with log.open('w',encoding='utf-8') as trace:
        process=subprocess.Popen([str(executable)],cwd=str(executable.parent),
                                 env=env,stdout=trace,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+hold_seconds
            while time.monotonic()<deadline:
                if process.poll() is not None:
                    raise RuntimeError(f'Installed Windows desktop exited early: code={process.returncode}')
                time.sleep(.25)
            evidence=dict(installed_windows_gui_started=True,
                          remained_running_seconds=hold_seconds,
                          in_place_installation=True,
                          isolated_ci_runner=True)
            (output/'windows-installed-desktop.json').write_text(
                json.dumps(evidence,sort_keys=True),encoding='utf-8')
            print('PASS: in-place upgraded installed Windows companion GUI remains running',flush=True)
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=12)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


if __name__=='__main__':
    smoke()