"""Regression: a RANDOM contiguous streak persists unlit until today qualifies.

Exercises the actual FastAPI/SQLite review ledger, not just a mathematical
example; Android's instrumentation test checks the real RemoteViews separately.
"""
from datetime import datetime, timedelta, timezone
import secrets
from fastapi.testclient import TestClient
from server.main import create_app


def test_random_streak_does_not_reset_on_incomplete_day_then_increments(tmp_path):
    n = 3 + secrets.randbelow(65)
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    timestamp_ms = int(now.timestamp() * 1000)
    token = "streak-randomized-test-token-2026"
    client = TestClient(create_app(tmp_path, token=token, clock=lambda: timestamp_ms),
                        headers={"Authorization": "Bearer " + token})
    settings = client.get("/v1/settings").json()
    settings.update(timezone="UTC", rollover_minute=0, lesson_answers=5, lesson_ms=0)
    assert client.put("/v1/settings", json=settings).status_code == 200

    # Actually create 5 native-like review events on each of N consecutive days.
    events = []
    for days_ago in range(n, 0, -1):
        day = now - timedelta(days=days_ago)
        for i in range(5):
            events.append(dict(collection_id="primary",
                               revlog_id=int(day.timestamp() * 1000) + i * 1000,
                               card_id=100000 + days_ago * 10 + i,
                               duration_ms=2000, rating=3))
    assert client.post("/v1/events", json={"device_id": "phone", "events": events}).status_code == 200
    s = client.get("/v1/state").json()
    assert s["streak"] == n and not s["completed"], (n, s["streak"])
    assert s["progress"]["answers"] == 0

    today = []
    for i in range(5):
        today.append(dict(collection_id="primary", revlog_id=timestamp_ms + i * 1000,
                          card_id=200000 + i, duration_ms=2000, rating=3))
    # Input event timestamp may be after clock if hour 12:00 and incremental;
    # server permits up to +5 minutes, as native events can have clock skew.
    assert client.post("/v1/events", json={"device_id": "phone", "events": today[:4]}).status_code == 200
    before = client.get("/v1/state").json()
    assert before["streak"] == n
    assert before["completed"] is False
    assert before["progress"]["answers"] == 4
    assert before["progress"]["remaining"] == 1
    assert client.post("/v1/events", json={"device_id": "phone", "events": today[4:]}).status_code == 200
    after = client.get("/v1/state").json()
    assert after["streak"] == n + 1
    assert after["completed"] is True
    assert after["progress"]["answers"] == 5
    assert after["progress"]["remaining"] == 0
    # Repeated upload of same answer must not inflate streak or activity.
    dup = client.post("/v1/events", json={"device_id": "phone", "events": today[4:]})
    assert dup.status_code == 200 and dup.json()["inserted"] == 0
    assert client.get("/v1/state").json()["streak"] == n + 1
    print(f"RANDOMIZED_STREAK_PASS: before={n}, after={n+1}, goal=5, today=4→5")
