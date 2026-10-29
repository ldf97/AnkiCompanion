from pathlib import Path
import tempfile, zipfile, shutil, stat, re
from app.skin_packs import load_pack, safe_rel, PackError

VERSION = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$')

class Packs:
    def __init__(self, bundled, installed):
        self.bundled, self.installed = Path(bundled), Path(installed)
        self.installed.mkdir(parents=True, exist_ok=True)
        self._cache = None

    def list(self):
        if self._cache is not None: return self._cache
        result = {}
        for manifest in list(self.bundled.glob('*/skin.json')) + list(self.installed.glob('*/*/skin.json')):
            skin = load_pack(manifest.parent)
            result[(skin['id'], skin['version'])] = (skin, manifest.parent)
        self._cache = result
        return result

    def get(self, identity, version):
        try: return self.list()[(identity, version)]
        except KeyError as exc: raise PackError('Skin version not installed') from exc

    def install(self, archive):
        if Path(archive).stat().st_size > 50 * 1024 * 1024:
            raise PackError('ZIP exceeds 50 MiB')
        with tempfile.TemporaryDirectory(dir=self.installed) as temp:
            root = Path(temp)
            with zipfile.ZipFile(archive) as zipf:
                entries = zipf.infolist()
                if len(entries) > 140 or sum(x.file_size for x in entries) > 100 * 1024 * 1024:
                    raise PackError('Skin exceeds unpacked limits')
                seen = set()
                for item in entries:
                    rel = safe_rel(item.filename.rstrip('/'))
                    folded = str(rel).casefold()
                    if folded in seen or stat.S_ISLNK(item.external_attr >> 16):
                        raise PackError('Duplicate path or symlink')
                    seen.add(folded)
                    if item.is_dir(): continue
                    if rel.suffix.lower() not in {'.json', '.png', '.jpg', '.jpeg', '.webp', '.svg'}:
                        raise PackError('Packs may contain only data and media')
                    target = root.joinpath(*rel.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zipf.open(item) as source, target.open('wb') as dest:
                        shutil.copyfileobj(source, dest)
            skin = load_pack(root)
            if not VERSION.fullmatch(skin['version']): raise PackError('Unsafe skin version')
            if (skin['id'], skin['version']) in self.list():
                raise PackError('Skin versions are immutable; increment version before importing')
            dest = self.installed / skin['id'] / skin['version']
            dest.parent.mkdir(parents=True, exist_ok=True)
            root.rename(dest)
            self._cache = None
            return skin

    def export(self, identity, version, destination):
        _, root = self.get(identity, version)
        with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for path in sorted(root.rglob('*')):
                if path.is_file(): zipf.write(path, path.relative_to(root).as_posix())
        return Path(destination)
