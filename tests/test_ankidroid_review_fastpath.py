"""Prove the companion layer cannot add per-card synchronous deck scans.

The pinned AnkiDroid Android build and native cross-device tests validate the
overlay against actual AnkiDroid source.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_deck_tree_scanned_only_when_queue_exhausted():
    source = (ROOT / "ankidroid_bridge" / "CompanionIntegration.kt").read_text()
    overlay = (ROOT / "ankidroid_bridge" / "apply.py").read_text()
    assert "suspend fun advanceWhenEmpty(): Boolean" in source
    assert "sched.deckDueTree()" in source
    assert "CompanionIntegration.beforeReview()" not in overlay
    assert "state == null && com.ichi2.anki.CompanionIntegration.advanceWhenEmpty()" in overlay
    assert "state == null && CompanionIntegration.advanceWhenEmpty()" in overlay
    assert "decks.select(next.did)" in source


def test_active_review_protects_card_press_from_native_network_sync():
    source = (ROOT / "ankidroid_bridge" / "CompanionIntegration.kt").read_text()
    assert "registerActivityLifecycleCallbacks(" in source
    assert "visibleReviewers.get() > 0" in source
    assert "if (requested.get()) requestSync()" in source
    assert "if (visibleReviewers.get() > 0) break" in source


def test_both_reviewer_styles_have_review_and_undo_hooks():
    source = (ROOT / "ankidroid_bridge" / "CompanionIntegration.kt").read_text()
    overlay = (ROOT / "ankidroid_bridge" / "apply.py").read_text()
    assert 'putBoolean("newReviewer"' not in source
    assert "legacy=base+'Reviewer.kt'" in overlay
    assert "val latest = getCard(card.id)" in overlay
    assert "latest.reps != card.reps" in overlay
    assert "if (answer == null)" in overlay
    assert "CompanionIntegration.isCurrent(card)" not in overlay
    # All reviewer answer/undo hooks must return immediately, with wake IPC
    # and native sync orchestration queued on the IO dispatcher.
    assert overlay.count("CompanionIntegration.reviewChanged()") == 6
    assert "fun reviewChanged()" in source
    assert "scope.launch {" in source
    assert "reviewEventQueued.compareAndSet(false, true)" in source
    assert "reviewEventPending.set(true)" in source
    assert "if (reviewEventPending.get()) reviewChanged()" in source
    assert "CompanionIntegration.requestSync()" in overlay
    assert "AbstractFlashcardViewer.kt" in overlay
    assert "suspend fun isCurrent(" in source


def test_companion_widget_never_contends_with_active_reviewer_collection():
    integration=(ROOT/'ankidroid_bridge'/'CompanionIntegration.kt').read_text()
    sync=(ROOT/'android'/'app'/'src'/'main'/'java'/'org'/'ankicompanion'/'app'/'Sync.kt').read_text()
    assert 'putBoolean("reviewer_active", visibleReviewers.get() > 0)' in integration
    assert 'getBoolean("reviewer_active",false)==true' in sync
    # Stop before revlog / decks / native sync: the separate app may never
    # acquire the Anki collection lock while card buttons are active.
    assert sync.index('if(reviewing) {') < sync.index('AnkiBridge.refreshNative(context)')
    assert sync.index('return store.load("state.json")?.let { cached ->') < sync.index('outbox.scan(')
    assert 'AnkiBridge.synchronize(context)' in sync
    assert 'if (requested.get()) requestSync()' in integration
