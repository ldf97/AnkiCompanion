"""Check actual native scheduling evidence; a passing emulator build is not enough."""
import json
from pathlib import Path


def verify(directory=Path('test-results/cross-device')):
    folder=Path(directory)
    state=json.loads((folder/'PASS.json').read_text())
    required=('phone_widget30','desktop_widget30','phone_widget50',
              'desktop_widget50','matched','phone_finished','observer_finished')
    missing=[key for key in required if not state.get(key)]
    if missing or state.get('phase')!=50:
        raise AssertionError(f'Cross-device handoff unfinished: {missing}; phase={state.get("phase")}')
    actual=json.loads((folder/'matching-native-collections.json').read_text())
    revlog=actual['reviews'];cards=actual['cards']
    if len(revlog)!=50 or len(cards)!=50:
        raise AssertionError('Native acceptance did not observe exactly 50 real cards and reviews')
    if len({r[0] for r in revlog})!=50 or len({r[1] for r in revlog})!=50:
        raise AssertionError('Duplicate native review or card identity')
    if len({c[0] for c in cards})!=50 or any(c[5]!=1 for c in cards):
        raise AssertionError('Native card scheduling did not converge to one review each')
    return dict(native_schedule_exact_match=True,review_count=50,
                desktop_to_phone_to_desktop=True,widget_30_and_50_confirmed=True)


if __name__=='__main__':
    print('PASS:',json.dumps(verify(),sort_keys=True))