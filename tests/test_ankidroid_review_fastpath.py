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
    assert "CompanionIntegration.isCurrent(card)" in overlay
    assert "CompanionIntegration.changed()" in overlay
    assert "CompanionIntegration.requestSync()" in overlay
    assert "AbstractFlashcardViewer.kt" in overlay
    assert "suspend fun isCurrent(" in source
