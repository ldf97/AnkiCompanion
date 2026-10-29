from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import hashlib, re

def lesson_progress(answers, duration_ms, policy):
    goal = policy['lesson_answers']; seconds_goal = policy['lesson_ms']
    return dict(answers=answers, duration_ms=duration_ms, goal=goal,
                remaining=max(0, goal-answers), percent=min(100, answers*100//goal),
                lesson_percent=min(100, int(100*min(answers/goal, duration_ms/seconds_goal if seconds_goal else 1))))


def study_day(timestamp_ms, timezone='America/New_York', rollover=0):
    local = datetime.fromtimestamp(timestamp_ms / 1000, ZoneInfo(timezone))
    day = local.date()
    if local.hour * 60 + local.minute < rollover:
        day -= timedelta(days=1)
    return day.isoformat()


def daily_lineup(day, skin, seed):
    """Deterministic on every device; independent choices per date/skin/key."""
    def pick(pool, key):
        message = '\x1f'.join([seed, day, skin['id'], skin['version'], key])
        index = int.from_bytes(hashlib.sha256(message.encode()).digest()[:8], 'big') % len(pool)
        return pool[index]
    shared = {key: pick(pool, 'background:' + key)
              for key, pool in skin['background_pools'].items()}
    records = {}
    for slot in skin['time_slots'] + [skin['completion']]:
        key = slot['id']; quote = pick(slot['quotes'], key + ':quote')
        bg = slot['background']; mode = bg['mode']
        background = (None if mode == 'none' else bg['asset'] if mode == 'fixed'
                      else shared[bg['pool']] if mode == 'shared'
                      else pick(skin['background_pools'][bg['pool']], key + ':background'))
        records[key] = dict(portrait=pick(slot['portraits'], key + ':portrait'),
                            quote=quote['text'], episode=quote.get('source', ''), background=background)
    return dict(date=day, skin_id=skin['id'], skin_version=skin['version'], records=records)


def next_deck(decks, parent_id, mode='new_and_reviews'):
    parent = next((d for d in decks if str(d['id']) == str(parent_id)), None)
    if parent is None:
        return None
    def eligible(d):
        return d['new'] > 0 or (mode == 'new_and_reviews' and d['review'] + d['learning'] > 0)
    prefix = parent['name'] + '::'
    children = [d for d in decks if d['name'].startswith(prefix)
                and '::' not in d['name'][len(prefix):]]
    def natural(d):
        return [(0, int(p)) if p.isdigit() else (1, p.casefold())
                for p in re.split(r'(\d+)', d['name'])]
    for child in sorted(children, key=natural):
        if eligible(child):
            return child
    # Scheduler parent totals include descendants. A remaining parent may have
    # cards directly in it, or a child excluded by a parent daily limit.
    return parent if eligible(parent) else None


def scene(skin, lineup, timestamp_ms, settings, completed, streak):
    local = datetime.fromtimestamp(timestamp_ms / 1000, ZoneInfo(settings['timezone']))
    minute = local.hour * 60 + local.minute
    slot = skin['completion'] if completed else next(
        s for s in skin['time_slots'] if s['start_minute'] <= minute < s['end_minute'])
    return dict(date=lineup['date'], time=local.strftime('%H:%M'),
                streak=streak, completed=completed, mood=slot['id'],
                **lineup['records'][slot['id']])
