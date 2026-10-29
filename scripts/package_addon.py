from pathlib import Path
import shutil,zipfile
root=Path(__file__).resolve().parents[1]
for name in ('rules.py','transport.py'):shutil.copy2(root/'companion'/name,root/'anki_addon'/name)
out=root/'packages';out.mkdir(exist_ok=True)
target=out/'Anki_Companion_Bridge.ankiaddon'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
    for path in sorted((root/'anki_addon').glob('*')):
        if path.is_file():z.write(path,path.name)
print(target)
