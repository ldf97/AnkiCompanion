from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
import sqlite3, json, secrets, time, threading
from companion.rules import study_day, daily_lineup, lesson_progress
from .models import Settings

class Conflict(ValueError): pass

class Store:
    def __init__(self, path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.tx() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                day TEXT NOT NULL, duration_ms INTEGER NOT NULL, retracted INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS by_day ON events(day);
            CREATE TABLE IF NOT EXISTS tombstones(id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS event_sources(id TEXT NOT NULL,device TEXT NOT NULL,seen_ms INTEGER NOT NULL,PRIMARY KEY(id,device));
            CREATE TABLE IF NOT EXISTS days(day TEXT PRIMARY KEY, policy TEXT NOT NULL, lineup TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots(device TEXT PRIMARY KEY, payload TEXT NOT NULL, updated INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY, device TEXT NOT NULL,
                payload TEXT NOT NULL, created INTEGER NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0);
            ''')
            db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', ('settings', Settings(revision=0).model_dump_json()))
            db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', ('seed', secrets.token_hex(24)))

    @contextmanager
    def tx(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=30)
            db.row_factory = sqlite3.Row
            try:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('BEGIN IMMEDIATE')
                yield db
                db.commit()
            except Exception:
                db.rollback(); raise
            finally: db.close()

    def _settings(self, db):
        return Settings.model_validate(json.loads(db.execute("SELECT value FROM meta WHERE key='settings'").fetchone()[0])).model_dump()

    def settings(self):
        with self.tx() as db: return self._settings(db)

    def update_settings(self, settings, packs=None, now_ms=None):
        with self.tx() as db:
            old = self._settings(db)
            if settings['revision'] != old['revision']: raise Conflict('Settings changed on another device; reload first')
            if any(settings[k] != old[k] for k in ('timezone', 'rollover_minute')) and db.execute('SELECT 1 FROM events LIMIT 1').fetchone():
                raise Conflict('Study timezone and rollover are fixed after the first event to preserve history')
            settings = dict(settings, revision=old['revision'] + 1)
            # A skin switch is visual, not a new study day. Rebuild today's
            # artwork immediately while preserving its frozen goal/policy and
            # every review event, completion state, and streak.
            skin_changed = any(settings[k] != old[k] for k in ('skin_id', 'skin_version'))
            if skin_changed and packs is None:
                raise ValueError('Skin changes require the installed skin catalog')
            current_day = study_day(now_ms if now_ms is not None else int(time.time()*1000),
                                    settings['timezone'], settings['rollover_minute'])
            if skin_changed:
                skin, _ = packs.get(settings['skin_id'], settings['skin_version'])
                seed = db.execute("SELECT value FROM meta WHERE key='seed'").fetchone()[0]
                lineup = daily_lineup(current_day, skin, seed)
                db.execute("UPDATE days SET lineup=? WHERE day=?",
                           (json.dumps(lineup), current_day))
            db.execute("UPDATE meta SET value=? WHERE key='settings'", (json.dumps(settings),))
            return settings

    def _day(self, db, day, packs):
        row = db.execute('SELECT * FROM days WHERE day=?', (day,)).fetchone()
        if row: return json.loads(row['policy']), json.loads(row['lineup'])
        settings = self._settings(db)
        skin, _ = packs.get(settings['skin_id'], settings['skin_version'])
        seed = db.execute("SELECT value FROM meta WHERE key='seed'").fetchone()[0]
        policy = {k: settings[k] for k in ('lesson_answers', 'lesson_ms', 'timezone', 'rollover_minute')}
        lineup = daily_lineup(day, skin, seed)
        db.execute('INSERT INTO days VALUES (?,?,?)', (day, json.dumps(policy), json.dumps(lineup)))
        return policy, lineup

    def add_events(self, events, packs, now_ms=None, device_id='unknown'):
        now_ms = now_ms or int(time.time() * 1000)
        with self.tx() as db:
            settings = self._settings(db); inserted = 0
            for event in events:
                if event.revlog_id > now_ms + 300_000: raise ValueError('Review event is in the future')
                if event.revlog_id < 946684800000: raise ValueError('Invalid review timestamp')
                payload = event.model_dump_json()
                db.execute('INSERT OR REPLACE INTO event_sources VALUES (?,?,?)',(event.key,device_id,now_ms))
                row = db.execute('SELECT payload FROM events WHERE id=?', (event.key,)).fetchone()
                if row:
                    # An older installation may have submitted a review without
                    # its rating. Enrich that record when a newer sender reports
                    # the same review; never count the same review twice.
                    previous = json.loads(row['payload'])
                    current = json.loads(payload)
                    for field in ('collection_id','revlog_id','card_id','duration_ms'):
                        if previous.get(field) != current.get(field):
                            raise Conflict('Event ID reused with different contents')
                    old_rating = previous.get('rating')
                    new_rating = current.get('rating')
                    if old_rating is not None and new_rating is not None and old_rating != new_rating:
                        raise Conflict('Event rating conflicts with existing review')
                    if old_rating is None and new_rating is not None:
                        previous['rating'] = new_rating
                        db.execute('UPDATE events SET payload=? WHERE id=?', (json.dumps(previous),event.key))
                    continue
                day = study_day(event.revlog_id, settings['timezone'], settings['rollover_minute'])
                self._day(db, day, packs)
                undone = bool(db.execute('SELECT 1 FROM tombstones WHERE id=?', (event.key,)).fetchone())
                db.execute('INSERT INTO events VALUES (?,?,?,?,?)', (event.key, payload, day, event.duration_ms, int(undone)))
                inserted += 1
            return dict(inserted=inserted, received=len(events))

    def retract(self, ids):
        with self.tx() as db:
            for identity in ids:
                if len(identity) > 250: raise ValueError('Event ID too long')
                db.execute('INSERT OR IGNORE INTO tombstones VALUES (?)', (identity,))
                db.execute('UPDATE events SET retracted=1 WHERE id=?', (identity,))

    def snapshot(self, snapshot, now_ms):
        with self.tx() as db:
            db.execute('INSERT OR REPLACE INTO snapshots VALUES (?,?,?)',
                (snapshot.device_id, snapshot.model_dump_json(), now_ms))

    def state(self, packs, now_ms):
        with self.tx() as db:
            settings = self._settings(db)
            today = study_day(now_ms, settings['timezone'], settings['rollover_minute'])
            policy, lineup = self._day(db, today, packs)
            rows = db.execute('SELECT day,COUNT(*) AS answers,COALESCE(SUM(duration_ms),0) AS ms FROM events WHERE retracted=0 GROUP BY day').fetchall()
            totals = {r['day']: dict(answers=r['answers'], duration_ms=r['ms']) for r in rows}
            goals = {r['day']: json.loads(r['policy']) for r in db.execute('SELECT day,policy FROM days')}
            complete = {d for d,t in totals.items() if t['answers'] >= goals[d]['lesson_answers']
                        and t['duration_ms'] >= goals[d]['lesson_ms']}
            done = today in complete
            cursor = date.fromisoformat(today) - timedelta(days=0 if done else 1); streak = 0
            while cursor.isoformat() in complete:
                streak += 1; cursor -= timedelta(days=1)
            devices = [dict(**json.loads(r['payload']), updated_ms=r['updated'])
                       for r in db.execute('SELECT * FROM snapshots ORDER BY updated DESC')]
            history = [dict(date=(date.fromisoformat(today)-timedelta(days=i)).isoformat(),
                            completed=(date.fromisoformat(today)-timedelta(days=i)).isoformat() in complete)
                       for i in reversed(range(7))]
            today_events = [dict(id=r['id'], duration_ms=r['duration_ms']) for r in
                db.execute('SELECT id,duration_ms FROM events WHERE day=? AND retracted=0', (today,))]
            progress=lesson_progress(**totals.get(today,dict(answers=0,duration_ms=0)),policy=policy)
            return dict(server_time_ms=now_ms, date=today, settings=settings, policy=policy,
                        lineup=lineup, seed=db.execute("SELECT value FROM meta WHERE key='seed'").fetchone()[0],
                        completed=done, streak=streak, progress=progress,
                        today_events=today_events, devices=devices, week=history)

    def enqueue(self, command, now_ms):
        identity = secrets.token_hex(12)
        with self.tx() as db:
            db.execute('INSERT INTO commands VALUES (?,?,?,?,0)',
                (identity, command.device_id, command.model_dump_json(), now_ms))
        return identity

    def commands(self, device, now_ms):
        with self.tx() as db:
            return [dict(id=r['id'], **json.loads(r['payload'])) for r in db.execute(
                'SELECT * FROM commands WHERE device=? AND acknowledged=0 AND created>=? ORDER BY created',
                (device, now_ms - 120_000))]

    def ack(self, identity, device):
        with self.tx() as db:
            db.execute('UPDATE commands SET acknowledged=1 WHERE id=? AND device=?', (identity, device))
