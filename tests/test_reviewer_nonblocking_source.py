from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_modified_ankidroid_no_network_sync_in_card_answer_and_before_review():
    source=(ROOT/'ankidroid_bridge'/'CompanionIntegration.kt').read_text()
    pre=source.split('suspend fun beforeReview()',1)[1].split('fun history(',1)[0]
    assert 'synchronize(notifyUi = false)' not in pre
    current=source.split('suspend fun isCurrent(',1)[1].split('suspend fun beforeReview',1)[0]
    assert 'synchronize(' not in current
    overlay=(ROOT/'ankidroid_bridge'/'apply.py').read_text()
    assert 'sched.answerCard(answer)' in overlay
    assert 'CompanionIntegration.requestSync()' in overlay

def test_launcher_entrypoint_is_crash_isolated():
    entry=(ROOT/'anki_addon'/'__init__.py').read_text()
    assert 'except BaseException as error:' in entry
    assert 'from . import bridge' in entry
    assert 'from .transport import Client' not in entry

def test_windows_addon_auto_provisioned_and_never_overwrites_collection():
    source=(ROOT/'desktop'/'bootstrap.py').read_text()
    assert 'ensure_anki_bridge()' in source
    assert 'collection.anki2' not in source
    assert 'meta.json' in source
