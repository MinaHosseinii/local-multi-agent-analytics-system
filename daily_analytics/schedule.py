"""Install/remove the daily job ON THE USER'S MAC, not in ChatGPT."""
import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = 'local.mina.daily-analytics'
ROOT = Path(__file__).resolve().parent.parent
PLIST = Path.home() / 'Library' / 'LaunchAgents' / f'{LABEL}.plist'


def job_definition(root, python):
    root = Path(root).absolute()
    return {
        'Label': LABEL,
        'ProgramArguments': [str(python), '-m', 'daily_analytics'],
        'WorkingDirectory': str(root),
        'StartCalendarInterval': {'Hour': 8, 'Minute': 0},
        'StandardOutPath': str(root / 'daily_reports' / 'scheduler.stdout.log'),
        'StandardErrorPath': str(root / 'daily_reports' / 'scheduler.stderr.log'),
        'EnvironmentVariables': {'PYTHONUNBUFFERED': '1'},
        'ProcessType': 'Background',
    }


def main():
    parser = argparse.ArgumentParser(description='Daily 08:00 macOS LaunchAgent.')
    parser.add_argument('action', choices=['install', 'status', 'remove'])
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('This scheduler must be installed on your Mac.')
    domain = f'gui/{os.getuid()}'
    service = f'{domain}/{LABEL}'
    if args.action == 'status':
        return subprocess.run(['launchctl', 'print', service], check=False).returncode
    if args.action == 'remove':
        subprocess.run(['launchctl', 'bootout', service], check=False)
        PLIST.unlink(missing_ok=True)
        print('Removed daily schedule. Existing reports remain.')
        return 0
    # Calendar intervals use the Mac's SYSTEM timezone; TZ env does not change that.
    zone = str(Path('/etc/localtime').resolve())
    if not zone.endswith('/Europe/Berlin'):
        parser.error('Set macOS system timezone to Europe/Berlin first. Calendar scheduling uses system local time.')
    (ROOT / 'daily_reports').mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    definition = job_definition(ROOT, os.path.abspath(sys.executable))
    if PLIST.exists():
        if plistlib.loads(PLIST.read_bytes()) != definition:
            parser.error('A different existing job has this label. Remove it explicitly before installing this one.')
        existing = subprocess.run(['launchctl', 'print', service], capture_output=True)
        if existing.returncode == 0:
            print('Schedule is already installed. Daily at 08:00 system time (Europe/Berlin).')
            return 0
    PLIST.write_bytes(plistlib.dumps(definition))
    subprocess.run(['launchctl', 'bootstrap', domain, str(PLIST)], check=True)
    subprocess.run(['launchctl', 'print', service], check=True, capture_output=True)
    print('Installed and verified: daily at 08:00 Europe/Berlin while your user session is available.')
    print('Sleep: runs after waking. Powered off: missed run is not guaranteed to catch up.')
    print('Keep the Mac awake/logged in for an on-time report. No model server is needed by default.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
