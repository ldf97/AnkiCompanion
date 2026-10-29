"""Brand-independent widget renderer for the existing Python visual prototype.

All scene pools, quotes, times, tint settings and icons are read from skin.json.
The drawing geometry and image treatment match the original Eren renderer.
This is NOT yet a compiled Android APK.
"""
from pathlib import Path
from datetime import date
from PIL import Image, ImageOps, ImageDraw, ImageFont
from functools import lru_cache
import io, json, random
try:
    import cairosvg
except (ImportError, OSError):
    cairosvg = None
from .skin_packs import load_pack

FONT_REG=str(Path(__file__).resolve().parents[1]/'fonts'/'DejaVuSans.ttf')
FONT_BOLD=str(Path(__file__).resolve().parents[1]/'fonts'/'DejaVuSans-Bold.ttf')

def cover(image,size):return ImageOps.fit(image.convert('RGB'),size,method=Image.Resampling.LANCZOS)
def fnt(sz,bold=False):return ImageFont.truetype(FONT_BOLD if bold else FONT_REG,sz)

def put_text(draw,txt,x,y,max_w):
    # Preserved verbatim from the previous renderer.
    for sz in (39,36,33,30,27,25):
        face=fnt(sz,True)
        lines=[]; cur=''
        for word in txt.split():
            nxt=(cur+' '+word).strip()
            if draw.textlength(nxt,font=face)<=max_w:cur=nxt
            else:
                if cur:lines.append(cur)
                cur=word
        if cur:lines.append(cur)
        if len(lines)<=3:break
    for line in lines:
        draw.text((x,y),line,font=face,fill='white',stroke_fill=(2,3,5),stroke_width=1)
        y+=sz+15

@lru_cache(maxsize=100)
def svg_icon(file, width, height):
    f=Path(file)
    if f.suffix.lower()=='.svg':
        if cairosvg is not None:
            png=cairosvg.svg2png(url=str(f),output_width=width,output_height=height)
        else:
            import resvg_py
            png=resvg_py.svg_to_bytes(svg_path=str(f),width=width,height=height)
        return Image.open(io.BytesIO(png)).convert('RGBA')
    return Image.open(f).convert('RGBA').resize((width,height),Image.Resampling.LANCZOS)

class WidgetEngine:
    def __init__(self, skin_dir, save_dir):
        self.skin_dir=Path(skin_dir)
        self.skin=load_pack(self.skin_dir)
        self.save_dir=Path(save_dir)
        self.save_dir.mkdir(parents=True,exist_ok=True)
        self.W=self.skin['canvas']['width'];self.H=self.skin['canvas']['height']
        self.style=self.skin['style']

    def path(self,rel):
        from .skin_packs import safe_rel
        return self.skin_dir.joinpath(*safe_rel(rel).parts)

    def get_row(self,hour,minute,completed):
        if completed:return self.skin['completion']
        time=hour*60+minute
        if not(0<=hour<24 and 0<=minute<60):raise ValueError('Invalid time')
        return next(s for s in self.skin['time_slots'] if s['start_minute']<=time<s['end_minute'])

    def red_tint_strength(self,hour,minute,completed=False):
        """Matches original: 0 through 10:00, ramp to .45 by 20:59, none 21:00+."""
        if not(0<=hour<=23 and 0<=minute<=59):raise ValueError('Invalid time')
        t=hour*60+minute
        start=self.style['red_tint_start_minute']
        end=self.style['red_tint_end_minute']
        if completed or t<=start or t>end:return 0.0
        return self.style['max_red_tint']*(t-start)/(end-start)

    def apply_red_tint(self,original,hour,minute,completed=False):
        strength=self.red_tint_strength(hour,minute,completed)
        if strength==0:return original.copy()
        overlay=Image.new('RGB',original.size,tuple(self.style['red_tint_rgb']))
        return Image.blend(original.convert('RGB'),overlay,strength)

    def warning_badge_visible(self,hour,minute,completed):
        return not completed and hour*60+minute>=self.style['warning_start_minute']

    def icon(self,key,width,height):
        return svg_icon(str(self.path(self.style['icons'][key])),width,height)

    def draw_warning_badge(self,canvas,scale=1.0):
        mini=self.style['warning_pulse_min_scale'];maxi=self.style['warning_pulse_max_scale']
        if not mini<=scale<=maxi:raise ValueError('Badge scale out of range')
        orig=self.icon('warning_badge',58,58)
        side=round(orig.width*scale)
        icon=orig.resize((side,side),Image.Resampling.LANCZOS)
        x,y=self.style['warning_badge_position']
        x-=round((side-orig.width)/2);y-=round((side-orig.height)/2)
        canvas.alpha_composite(icon,(x,y))

    def flame(self,canvas,x,y,lit):
        icon=self.icon('flame_lit' if lit else 'flame_unlit',67,75)
        canvas.alpha_composite(icon,(x,y))

    def verify_assets(self):
        # load_pack validates *all* referenced images and their readability.
        return load_pack(self.skin_dir)

    def _background(self,slot, shared_backgrounds, rng):
        spec=slot['background'];mode=spec['mode']
        if mode=='none':return None
        if mode=='fixed':return spec['asset']
        pool=spec['pool']
        if mode=='random':return rng.choice(self.skin['background_pools'][pool])
        if mode=='shared':return shared_backgrounds[pool]
        raise ValueError(f'Unknown background policy {mode}')

    def daily_lineup(self,day):
        """A date is drawn once and saved; refreshes do not reroll selections."""
        file=self.save_dir/f'daily_lineup_{day}.json'
        if file.exists():return json.loads(file.read_text(encoding='utf-8'))
        rng=random.SystemRandom()
        shared={}
        for slot in self.skin['time_slots']+[self.skin['completion']]:
            policy=slot['background']
            if policy['mode']=='shared' and policy['pool'] not in shared:
                shared[policy['pool']]=rng.choice(self.skin['background_pools'][policy['pool']])
        records={}
        for slot in self.skin['time_slots']+[self.skin['completion']]:
            portrait=rng.choice(slot['portraits'])
            quote=rng.choice(slot['quotes'])
            background=self._background(slot,shared,rng)
            records[slot['id']]=dict(portrait=portrait,quote=quote['text'],episode=quote.get('source',''),background=background)
        data={'date':day,'records':records}
        file.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
        return data

    def case_for(self,day,hour,minute,streak,completed=False):
        row=self.get_row(hour,minute,completed)
        lineup=self.daily_lineup(day)
        return dict(date=day,time=f'{hour:02d}:{minute:02d}',streak=streak,
                    completed=completed,mood=row['id'],**lineup['records'][row['id']])

    def render(self,case,out_dir=None,warning_scale=1.0,include_warning=True):
        # Preserves the original widget composition and coordinate geometry.
        out_dir=Path(out_dir) if out_dir is not None else self.save_dir
        out_dir.mkdir(parents=True,exist_ok=True)
        W,H=self.W,self.H
        done=case['completed']
        row=self.get_row(*map(int,case['time'].split(':')),done)
        portrait=cover(Image.open(self.path(case['portrait'])),(W,H) if done else (330,330))
        if done:base=portrait.convert('RGBA')
        else:
            base=cover(Image.open(self.path(case['background'])),(W,H))
            hour,minute=map(int,case['time'].split(':'))
            if row.get('tint',False):
                base=self.apply_red_tint(base,hour,minute,completed=done)
            base=base.convert('RGBA')
        shade=Image.new('RGBA',(W,H),(0,0,0,0));pixels=shade.load()
        for x in range(W):
            alpha=int(212*(1-x/W)**1.5)
            for y in range(H):pixels[x,y]=(4,5,7,alpha)
        base=Image.alpha_composite(base,shade)
        if not done:
            inset=Image.new('RGBA',(330,330));inset.paste(portrait,(0,0))
            mask=Image.new('L',(330,330));md=ImageDraw.Draw(mask)
            md.rounded_rectangle((0,0,329,329),radius=22,fill=255)
            base.paste(inset,(W-372,70),mask)
        d=ImageDraw.Draw(base)
        if not done:d.rounded_rectangle((W-372,70,W-42,400),radius=22,outline=(244,220,183),width=3)
        self.flame(base,41,52,done)
        if include_warning and not done and self.warning_badge_visible(hour,minute,done):
            self.draw_warning_badge(base,scale=warning_scale)
        d.text((128,64),str(case['streak']),font=fnt(76,True),fill='#fff0da')
        d.text((134,157),self.style['streak_label'],font=fnt(24),fill='#ffe3cc')
        put_text(d,case['quote'],52,255,660 if done else 620)
        name=f'frame_{case.get("case",1)}_{case["mood"]}.png'
        result=out_dir/name
        base.save(result)
        return result

    def render_cases(self,cases,out_dir=None):
        out_dir=Path(out_dir) if out_dir else self.save_dir
        out_dir.mkdir(parents=True,exist_ok=True)
        for case in cases:self.render(case,out_dir)
        # Existing 3-frame preview arrangement, unchanged.
        W,H=self.W,self.H
        sheet=Image.new('RGB',(W,3*(H+70)),'#111215')
        dr=ImageDraw.Draw(sheet)
        for i,c in enumerate(cases):
            p=out_dir/f'frame_{c.get("case",i+1)}_{c["mood"]}.png'
            sheet.paste(Image.open(p).convert('RGB'),(0,i*(H+70)+45))
            dr.text((15,i*(H+70)+12),f'Case {i+1} — {c["time"]} | {c["streak"]} days | {c["mood"]} | completed={c["completed"]}',font=fnt(20),fill='white')
        path=out_dir/'three_rendered_frames.png'
        sheet.save(path)
        return path
