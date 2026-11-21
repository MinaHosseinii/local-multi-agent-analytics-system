import argparse
import fcntl
import json
import shutil
import sys
from pathlib import Path

from .engine import run

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = Path(__file__).resolve().parent / 'config.json'


def main():
    parser = argparse.ArgumentParser(description='Unattended, local daily order-line analytics.')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--init-demo', action='store_true', help='Create synthetic demo input only if absent.')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if args.init_demo:
        destination = ROOT / config['input_csv']
        if destination.exists():
            parser.error('Input already exists; it was not replaced.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(__file__).parent / 'examples' / 'clean_orders.csv', destination)
        print('Created SYNTHETIC demo export:', destination)
        return 0
    output = ROOT / config['output_directory']
    output.mkdir(parents=True, exist_ok=True)
    with (output / '.daily.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another daily run is in progress. No duplicate run started.')
            return 0
        try:
            report = run(ROOT, config)
        except Exception as error:
            print(f'Run failed: {type(error).__name__}: {error}', file=sys.stderr)
            return 1
        print('Status:', report['status'])
        print('Report:', Path(report['run_directory']) / 'report.html')
        print('Evidence:', Path(report['run_directory']) / 'report.json')
        # A quality failure is a delivered alert, not a silently successful analysis.
        return 0 if report['status'] == 'completed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
