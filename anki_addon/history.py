"""Collection reads stay on Anki's GUI thread; this module has no Qt dependency."""
import json


def reconcile(collection_db, outbox_db, collection_id, cursor, recent_floor):
    rows = collection_db.all('SELECT id,cid,time,ease,ivl,lastIvl FROM revlog WHERE id>=? AND ease>0 ORDER BY id LIMIT 1000', cursor)
    recent = collection_db.all('SELECT id,cid,time,ease,ivl,lastIvl FROM revlog WHERE id>=? AND ease>0 ORDER BY id', recent_floor)
    for rid, cid, duration, rating, interval, last_interval in rows + recent:
        payload = dict(collection_id=collection_id, revlog_id=rid, card_id=cid,
                       duration_ms=min(600000, max(0, duration)),rating=rating,
                       interval=interval,previous_interval=last_interval)
        identity=f'{collection_id}:{rid}:{cid}'
        inserted=outbox_db.execute('INSERT OR IGNORE INTO outbox VALUES (?,?,0)',
                                  (identity,json.dumps(payload)))
        if inserted.rowcount==0:
            previous=outbox_db.execute('SELECT payload FROM outbox WHERE id=?',(identity,)).fetchone()
            if previous and 'rating' not in json.loads(previous[0]):
                outbox_db.execute('UPDATE outbox SET payload=?,sent=0 WHERE id=?',
                                  (json.dumps(payload),identity))
    # Reconcile all previously observed rows, including older undo/deletions.
    # A newly imported record may have an ID below the cursor: reset the cursor
    # after each completed collection sync, then page through the backfill again.
    # Bound every GUI-thread pass: a large medical Anki collection can have
    # hundreds of thousands of reviews. Never rescan the entire outbox on
    # each five-second timer. Unsynced and recent entries take priority.
    known = [(i, json.loads(p)) for i,p in outbox_db.execute(
        'SELECT id,payload FROM outbox ORDER BY sent ASC, rowid DESC LIMIT 1200')]
    known = [(i,p) for i,p in known if p['collection_id'] == collection_id]
    for offset in range(0, len(known), 300):
        batch = known[offset:offset+300]
        marks = ','.join('?' for _ in batch)
        present = set(collection_db.list(f'SELECT id FROM revlog WHERE ease>0 AND id IN ({marks})',
                                         *[p['revlog_id'] for _,p in batch]))
        for identity,payload in batch:
            if payload['revlog_id'] not in present:
                outbox_db.execute('INSERT OR IGNORE INTO undo VALUES (?,0)', (identity,))
    return rows[-1][0]+1 if rows else cursor
