"""Skin format validation and safe local ZIP import for the prototype.

Artwork is intentionally separate from application code. A pack is a ZIP
containing skin.json and its referenced media, at the ZIP root.
"""
from pathlib import Path, PurePosixPath
import json, re, shutil, stat, tempfile, zipfile
from xml.etree import ElementTree
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT/'skins'
PACK_ID_RE = re.compile(r'^[a-z][a-z0-9_-]{1,45}$')
MEDIA_EXT = {'.png', '.jpg', '.jpeg', '.webp'}
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_UNPACKED_BYTES = 100 * 1024 * 1024
MAX_FILES = 140

class PackError(ValueError):pass

def safe_rel(value):
    if not isinstance(value,str) or not value or '\\' in value or '\x00' in value:
        raise PackError(f'Invalid asset path: {value!r}')
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in ('..','.') for x in value.split('/')) or value.startswith('/'):
        raise PackError(f'Asset path escapes pack: {value!r}')
    return p

def _media(root, value, icon=False):
    p = safe_rel(value)
    extension=p.suffix.lower()
    if extension not in (MEDIA_EXT|{'.svg'} if icon else MEDIA_EXT):
        raise PackError(f'Unsupported {"icon" if icon else "image"}: {value!r}')
    f=root.joinpath(*p.parts)
    if not f.is_file() or f.is_symlink() or not f.resolve().is_relative_to(root.resolve()):
        raise PackError(f'Asset missing or unsafe: {value}')
    if extension=='.svg':
        raw=f.read_bytes()
        if len(raw)>100_000 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise PackError(f'Unsafe SVG file: {value}')
        tree=ElementTree.fromstring(raw)
        allowed={'svg','title','defs','linearGradient','radialGradient','stop','path','rect','circle','ellipse','g'}
        for element in tree.iter():
            tag=element.tag.rsplit('}',1)[-1]
            if tag not in allowed or any(k.rsplit('}',1)[-1].lower() in {'href','style','onload','onclick'} or k.lower().startswith('on') for k in element.attrib):
                raise PackError(f'SVG contains unsupported content: {value}')
            for attr_value in element.attrib.values():
                if 'url(' in attr_value.lower() and not re.fullmatch(r'url\(#[a-zA-Z0-9_-]+\)', attr_value.strip()):
                    raise PackError(f'SVG contains nonlocal reference: {value}')
    else:
        with Image.open(f) as img:
            if img.width > 8192 or img.height > 8192 or img.width*img.height>30_000_000:
                raise PackError(f'Image too large: {value}')
            img.verify()

def load_pack(root):
    root=Path(root)
    manifest=root/'skin.json'
    if not manifest.is_file():raise PackError('skin.json missing at pack root')
    if manifest.stat().st_size>200_000:raise PackError('skin.json excessively large')
    pack=json.loads(manifest.read_text(encoding='utf-8'))
    if pack.get('schema_version')!=1:raise PackError('Unsupported schema version (expected 1)')
    if not PACK_ID_RE.fullmatch(pack.get('id','')):raise PackError('Invalid pack ID')
    if not isinstance(pack.get('name'),str) or not pack['name'].strip():raise PackError('Missing pack name')
    version=pack.get('version')
    if not isinstance(version,str) or len(version)>40:raise PackError('Missing/invalid pack version')
    canvas=pack.get('canvas',{})
    if canvas.get('width')!=1100 or canvas.get('height')!=468:
        raise PackError('Prototype v1 uses a fixed 1100x468 layout')
    slots=pack.get('time_slots',[])
    if not isinstance(slots,list) or not slots:raise PackError('No time slots')
    if slots[0]['start_minute']!=0 or slots[-1]['end_minute']!=1440:
        raise PackError('Time slots must cover entire day')
    for a,b in zip(slots,slots[1:]):
        if a['end_minute']!=b['start_minute']:raise PackError('Time slots have a gap or overlap')
    seen=set()
    pools=pack.get('background_pools',{})
    for name,assets in pools.items():
        if not isinstance(assets,list) or not assets:raise PackError(f'Empty background pool: {name}')
        for asset in assets:_media(root,asset)
    for slot in slots+[pack['completion']]:
        if not isinstance(slot.get('id'),str) or not slot['id'] or slot['id'] in seen:
            raise PackError('Duplicate/invalid slot id')
        seen.add(slot['id'])
        if slot in slots:
            start,end=slot['start_minute'],slot['end_minute']
            if not (0 <= start < end <=1440):raise PackError('Invalid slot times')
        if not isinstance(slot.get('portraits'),list) or not slot['portraits']:
            raise PackError('Each slot must have at least one portrait')
        for asset in slot['portraits']:_media(root,asset)
        if not isinstance(slot.get('quotes'),list) or not slot['quotes']:
            raise PackError('Each slot must have at least one quote')
        for item in slot['quotes']:
            if not isinstance(item.get('text'),str) or not item['text'].strip() or len(item['text'])>1000:
                raise PackError('Invalid quote')
            if not isinstance(item.get('source',''),str):raise PackError('Invalid quote source')
        bg=slot.get('background',{})
        mode=bg.get('mode')
        if mode=='fixed':_media(root,bg['asset'])
        elif mode in ('random','shared'):
            if bg.get('pool') not in pools:raise PackError(f'Unknown background pool: {bg}')
        elif mode!='none':raise PackError(f'Unknown background mode: {mode}')
    if pack['completion']['background']['mode']!='none':
        raise PackError('Completion uses full-bleed portrait; background must be none')
    s=pack.get('style',{})
    if not 0 <= s.get('max_red_tint',-1) <= 1:raise PackError('Tint outside 0..1')
    if not 0 <= s.get('red_tint_start_minute',-1) < s.get('red_tint_end_minute',-1) < 1440:
        raise PackError('Invalid red tint time range')
    if not 0 <= s.get('warning_start_minute',-1) <= 1440:raise PackError('Invalid warning start')
    if len(s.get('red_tint_rgb',[]))!=3 or any(type(v)!=int or not 0<=v<=255 for v in s['red_tint_rgb']):
        raise PackError('Invalid red RGB target')
    if s.get('warning_pulse_min_scale')!=1.0 or not 1.0<=s.get('warning_pulse_max_scale',0)<=2:
        raise PackError('Invalid pulse settings')
    for asset in s['icons'].values():_media(root,asset,icon=True)
    return pack

def import_zip(archive, replace=False):
    """Install an image/quote-only skin pack; never execute pack-supplied code."""
    archive=Path(archive)
    if archive.stat().st_size>MAX_ZIP_BYTES:raise PackError('Archive too large')
    PACKS.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist()
        if len(infos)>MAX_FILES:raise PackError('Too many files')
        if sum(i.file_size for i in infos)>MAX_UNPACKED_BYTES:
            raise PackError('Archive expands beyond size limit')
        names=set()
        for i in infos:
            if i.filename in names:raise PackError('Duplicate ZIP entry')
            names.add(i.filename)
            safe_rel(i.filename.rstrip('/'))
            if stat.S_ISLNK(i.external_attr>>16):raise PackError('Symbolic links not allowed')
            if not i.is_dir() and PurePosixPath(i.filename).suffix.lower() not in (MEDIA_EXT|{'.svg','.json'}):
                raise PackError(f'Only images, SVG icons and JSON allowed in skin packs: {i.filename}')
        with tempfile.TemporaryDirectory(dir=PACKS,prefix='.import_') as td:
            temp=Path(td)
            z.extractall(temp)
            manifest=load_pack(temp)
            destination=PACKS/manifest['id']
            if destination.exists():
                if not replace:raise PackError('Pack exists; use --replace explicitly')
                # Validate new pack in full before replacing the existing version.
                backup=PACKS/('.previous_'+manifest['id'])
                if backup.exists():shutil.rmtree(backup)
                destination.rename(backup)
                try:shutil.copytree(temp,destination)
                except Exception:
                    backup.rename(destination)
                    raise
                shutil.rmtree(backup)
            else:shutil.copytree(temp,destination)
    return destination
