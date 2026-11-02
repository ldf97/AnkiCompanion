"""Stable fingerprint of *confirmed* shared state across connected devices.

The server computes it once from the same database snapshot used for the
response. Device-specific receipts and local pending estimates are excluded.
"""
import hashlib
import json


def shared_revision(state):
    fields = ('date', 'settings', 'policy', 'lineup', 'seed', 'completed',
              'streak', 'progress', 'today_events', 'week')
    shared = {key: state[key] for key in fields}
    document = json.dumps(shared, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True).encode('utf-8')
    return hashlib.sha256(document).hexdigest()
