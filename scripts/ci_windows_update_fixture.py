"""Inject test-only GUI automation and loopback release fixtures into a disposable Windows build.

This script ONLY changes the isolated GitHub runner workspace. No CI fixtures,
trust exceptions or auto-click logic are committed to production sources.
"""
import json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/"test-results"/"update-buttons"/"windows"
APP=ROOT/"desktop"/"app.py"
UPDATES=ROOT/"companion"/"updates.py"
VERSION=ROOT/"VERSION.json"


def replace(source, before, after):
    if before not in source:
        raise RuntimeError(f"Could not patch expected source anchor: {before[:110]}")
    return source.replace(before,after,1)


def enable_baseline():
    WORK.mkdir(parents=True,exist_ok=True)
    (WORK/"original-desktop.py").write_bytes(APP.read_bytes())
    (WORK/"original-updates.py").write_bytes(UPDATES.read_bytes())
    (WORK/"original-version.json").write_bytes(VERSION.read_bytes())

    original=APP.read_text(encoding='utf-8')
    trigger="""        if autostart and os.environ.get('ANKI_COMPANION_CI_UPGRADE')=='1':
            def _test_click_update():
                Path(os.environ['ANKI_COMPANION_CI_MARKERS'],'clicked-update-button.txt').write_text(
                    'Qt QPushButton.click reached real update handler')
                self.update_button.click()
            QTimer.singleShot(4000,_test_click_update)

"""
    original=replace(original,"    def repair_setup(self):",trigger+"    def repair_setup(self):")
    original=replace(original,
        """if QMessageBox.question(self,'Update to '+release['version'],text+'\\n\\nDownload and update?')==QMessageBox.StandardButton.Yes:""",
        """if (QMessageBox.StandardButton.Yes if os.environ.get('ANKI_COMPANION_CI_UPGRADE')=='1' else QMessageBox.question(self,'Update to '+release['version'],text+'\\n\\nDownload and update?'))==QMessageBox.StandardButton.Yes:""")
    APP.write_text(original,encoding='utf-8')

    source=UPDATES.read_text(encoding='utf-8')
    helpers='''
def _ci_release_open(request):
    if os.environ.get('ANKI_COMPANION_CI_UPGRADE')=='1':
        source=Path(os.environ['ANKI_COMPANION_CI_MANIFEST']).open('rb')
        class Fixture:
            def __enter__(self):return self
            def __exit__(self,*args):source.close()
            def read(self,n=-1):return source.read(n)
            def geturl(self):return PUBLIC_RELEASES+'update.json'
        return Fixture()
    return urllib.request.urlopen(request,timeout=20)


def _ci_asset_open(opener,request,release):
    if os.environ.get('ANKI_COMPANION_CI_UPGRADE')=='1':
        stream=Path(os.environ['ANKI_COMPANION_CI_ASSET']).open('rb')
        class Fixture:
            def __enter__(self):return self
            def __exit__(self,*args):stream.close()
            def read(self,n=-1):return stream.read(n)
            def geturl(self):return release['download_url']
        return Fixture()
    return opener.open(request,timeout=60)

'''
    source=replace(source,"def github_release(platform='windows'):",helpers+"def github_release(platform='windows'):")
    source=replace(source,'with urllib.request.urlopen(req,timeout=20) as response:',
                   'with _ci_release_open(req) as response:')
    source=replace(source,'with opener.open(request,timeout=60) as source,temp.open(\'wb\') as target:',
                   'with _ci_asset_open(opener,request,release) as source,temp.open(\'wb\') as target:')
    source=replace(source,'        temp.replace(dest);return dest',
        '''        temp.replace(dest)
        if os.environ.get('ANKI_COMPANION_CI_UPGRADE')=='1':
            Path(os.environ['ANKI_COMPANION_CI_MARKERS'],'downloaded-verified-installer.txt').write_text(
                f"Verified SHA-256: {digest.hexdigest()} / {size} bytes")
        return dest''')
    source=replace(source,
        "    subprocess.Popen([str(package),'/CURRENTUSER','/RESTARTAPPLICATIONS'],close_fds=True)",
        """    if os.environ.get('ANKI_COMPANION_CI_UPGRADE')=='1':
        Path(os.environ['ANKI_COMPANION_CI_MARKERS'],'launched-verified-installer.txt').write_text(
            f"Qt Update handler launched {package.name}")
        args=[str(package),'/CURRENTUSER','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/AUTOUPDATE']
    else:
        args=[str(package),'/CURRENTUSER','/RESTARTAPPLICATIONS']
    subprocess.Popen(args,close_fds=True)""")
    UPDATES.write_text(source,encoding='utf-8')


def restore_and_patch_target():
    APP.write_bytes((WORK/"original-desktop.py").read_bytes())
    UPDATES.write_bytes((WORK/"original-updates.py").read_bytes())
    s=APP.read_text(encoding='utf-8')
    s=replace(s,
        "self.update_button=QPushButton('App updates · '+updates.version()['version'])",
        "self.update_button=QPushButton('App updates · PATCH CONFIRMED · '+updates.version()['version'])")
    APP.write_text(s,encoding='utf-8')
    v=json.loads(VERSION.read_text(encoding='utf-8'))
    assert v['version']=='0.1.1',v
    v['version']='0.1.2';v['build']=v.get('build',2)+1
    VERSION.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    if sys.argv[1]=='enable-baseline':enable_baseline()
    elif sys.argv[1]=='restore-and-patch':restore_and_patch_target()
    else:raise SystemExit('Expected enable-baseline or restore-and-patch')
