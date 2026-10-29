"""Run a check with durable-on-disk evidence, then assemble the next checkpoint.

Usage: python scripts/run_logged.py 002-server.txt -- python -m pytest -v tests
The caller uploads the assembled checkpoint immediately after this exits.
"""
from pathlib import Path
from datetime import datetime, timezone
import subprocess, sys, time, json, os

root = Path(__file__).resolve().parents[1]
if len(sys.argv) < 4 or sys.argv[2] != '--':
    raise SystemExit(__doc__)
name = Path(sys.argv[1]).name
log_path = root/'test-results'/name
log_path.parent.mkdir(exist_ok=True)
if log_path.exists():
    raise SystemExit('Use a new log filename; previous test records are immutable')
started = time.monotonic()
with log_path.open('w', buffering=1) as log:
    log.write('Started UTC: '+datetime.now(timezone.utc).isoformat()+'\n')
    log.write('Command: '+json.dumps(sys.argv[3:])+'\n')
    log.write('Working directory: '+str(root)+'\n\n');log.flush();os.fsync(log.fileno())
    try:
        result = subprocess.run(sys.argv[3:], cwd=root, stdout=log, stderr=subprocess.STDOUT)
        code = result.returncode
    except Exception as exc:
        log.write(repr(exc)+'\n');code=127
    log.write(f'\nExit code: {code}\nElapsed seconds: {time.monotonic()-started:.3f}\n')
    log.flush();os.fsync(log.fileno())
print(log_path.read_text())
subprocess.run([sys.executable,str(root/'scripts/checkpoint.py')],cwd=root,check=True)
raise SystemExit(code)
