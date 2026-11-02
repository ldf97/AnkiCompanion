"""Monotonic review generations; only native syncs that start after upload may ACK."""


class ReviewEpoch:
    def __init__(self):
        self.answered = 0
        self.scanned = 0
        self.uploaded = 0
        self.synced = 0

    def answer(self):
        self.answered += 1
        return self.answered

    @property
    def needs_scan(self):
        return self.scanned < self.answered

    @property
    def needs_sync(self):
        return self.synced < self.answered

    def scan_complete(self):
        self.scanned = self.answered
        return self.scanned

    def upload_complete(self, captured_generation):
        # The worker may finish after another answer. Do not ACK later work.
        self.uploaded = max(self.uploaded, min(captured_generation, self.scanned))

    def sync_started(self):
        # The collection sync cannot acknowledge answers that have not been
        # captured by review-history reconciliation AND sent to the server.
        return min(self.scanned, self.uploaded)

    def sync_complete(self, started_generation):
        self.synced = max(self.synced, min(started_generation, self.uploaded))
        return not self.needs_sync
