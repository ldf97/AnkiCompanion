"""Actual HTTP gym-lab regression: 3 independent SQLite devices + API process."""
from pathlib import Path

from simulations.gym.lab import run_scenario


def test_gym_handoff_reconnect_undo_and_manual_conflict(tmp_path: Path):
    result=run_scenario(tmp_path/'gym')
    assert result['notification_seconds'] < 5
    assert len(result['native_schedule']) == 41  # 40 before conflict + 1 committed
    assert (tmp_path/'gym/gym-lab-report.json').is_file()
    names=[item['step'] for item in result['timeline']]
    assert any('Android process restarted' in name for name in names)
    assert any('HTTP server process restarted' in name for name in names)
    assert any('conflict preserved' in name for name in names)
