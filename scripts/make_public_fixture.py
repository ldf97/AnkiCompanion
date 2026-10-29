"""Create an independent neutral skin and cross-language test vectors.

Never reads or modifies personal artwork or quotes. Public binaries use this
fallback until the user imports their private pack from the continuation ZIP.
"""
from pathlib import Path
import json, shutil, sys
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from companion.rules import daily_lineup

def make():
    root=ROOT/'skins/study_companion';root.mkdir(parents=True,exist_ok=True)
    image=Image.new('RGB',(1100,468),'#192b3b');draw=ImageDraw.Draw(image)
    for x in range(1100):draw.line((x,0,x,468),fill=(20+x//80,35+x//45,50+x//35))
    image.save(root/'scene.png')
    shutil.copytree(ROOT/'assets/icons',root/'icons',dirs_exist_ok=True)
    slots=[]
    for identity,start,end in [('friendly',0,600),('pensive',600,900),('threatening',900,1080),('evening',1080,1260),('rumbling',1260,1440)]:
        slots.append(dict(id=identity,start_minute=start,end_minute=end,portraits=['scene.png'],
                          quotes=[dict(text='One answer at a time.',source='AnkiCompanion')],
                          background=dict(mode='fixed',asset='scene.png'),tint=600<=start<1260))
    skin=dict(schema_version=1,id='study_companion',name='Study Companion',version='1.0.0',
              canvas=dict(width=1100,height=468),background_pools={},time_slots=slots,
              completion=dict(id='freedom',portraits=['scene.png'],quotes=[dict(text='Daily lesson complete.',source='AnkiCompanion')],background=dict(mode='none')),
              style=dict(max_red_tint=.45,red_tint_start_minute=600,red_tint_end_minute=1259,
                         red_tint_rgb=[200,0,0],warning_start_minute=1080,warning_pulse_min_scale=1.0,
                         warning_pulse_max_scale=1.25,warning_pulse_duration_ms=1800,warning_badge_position=[95,35],
                         streak_label='day streak',icons=dict(flame_lit='icons/streak_flame_lit.svg',flame_unlit='icons/streak_flame_unlit.svg',warning_badge='icons/streak_warning_badge.svg')))
    (root/'skin.json').write_text(json.dumps(skin,indent=2))
    vectors=dict(skin=skin,seed='public-fixture',vectors=[dict(date=day,lineup=daily_lineup(day,skin,'public-fixture')) for day in ['2026-10-29','2026-10-30','2026-11-01']])
    fixture=ROOT/'android/app/src/test/resources/rules-vectors.json'
    fixture.parent.mkdir(parents=True,exist_ok=True);fixture.write_text(json.dumps(vectors,indent=2))
    print('Created neutral skin and public test vectors; personal assets untouched')

if __name__=='__main__':make()
