"""Run offline tests, including the separately named daily_analytics.tests suite."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


def main():
    root = Path(__file__).resolve().parent
    loader = unittest.TestLoader()
    suite = loader.discover(str(root), pattern='test_*.py', top_level_dir=str(root))
    suite.addTests(loader.loadTestsFromName('daily_analytics.tests'))
    # A mistaken branch in a test must fail, not contact a real model server.
    with patch('socket.create_connection', side_effect=RuntimeError('Network disabled in offline tests')):
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
