from pathlib import Path
import shutil,zipfile
root=Path(__file__).resolve().parents[1]
for name in ('rules.py','transport.py'):shutil.copy2(root/'companion'/name,root/'anki_addon'/name)
out=root/'packages';out.mkdir(exist_ok=True)
target=out/'Anki_Companion_Bridge.ankiaddon'
# Explicit, version-controlled inventory; installer and acceptance validate it.
ADDON_SOURCE_FILES=('__init__.py','bridge.py','history.py','rules.py',
                    'transport.py','review_epoch.py','config.json','config.md','manifest.json')
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
    for name in ADDON_SOURCE_FILES:
        z.write(root/'anki_addon'/name,name)
print(target)
