"""Regression for hot-path AnkiDroid review responsiveness.

Compilation and real native cross-device tests still gate the review hooks in CI.
This source contract prevents reintroducing full-deck scans per card.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_deck_tree_traversal_is_not_on_normal_reviewer_transition():
    source=(ROOT/'ankidroid_bridge'/'CompanionIntegration.kt').read_text(encoding='utf-8')
    before=source.split('    suspend fun beforeReview() {',1)[1].split('\n    fun history(',1)[0]
    assert 'val counts = sched.counts()' in before
    assert 'if (hasEligibleCards) return@withCol' in before
    assert before.index('if (hasEligibleCards) return@withCol') < before.index('sched.deckDueTree()')
    assert 'changed()' not in before
    # The device still switches decks when its selected deck is exhausted.
    assert 'decks.select(next.did)' in before
    assert 'clearance != "new_only"' in before


def test_native_sync_and_stale_card_guard_remain_enabled():
    integration=(ROOT/'ankidroid_bridge'/'CompanionIntegration.kt').read_text(encoding='utf-8')
    overlay=(ROOT/'ankidroid_bridge'/'apply.py').read_text(encoding='utf-8')
    assert 'fun requestSync()' in integration
    assert 'suspend fun isCurrent(' in integration
    assert 'CompanionIntegration.beforeReview()' in overlay
    assert 'CompanionIntegration.isCurrent(card)' in overlay
    assert 'CompanionIntegration.requestSync()' in overlay
