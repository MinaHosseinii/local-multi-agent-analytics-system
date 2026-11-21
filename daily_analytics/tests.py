import copy
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from .engine import read_export, run
from .schedule import job_definition

PACKAGE = Path(__file__).parent


class TestDailyAnalytics(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = json.loads((PACKAGE / 'config.json').read_text())
        self.now = datetime(2026, 11, 19, 8, tzinfo=ZoneInfo('Europe/Berlin'))
        self.source = self.root / self.config['input_csv']
        self.source.parent.mkdir()
        self.example('clean_orders.csv')

    def example(self, name):
        shutil.copyfile(PACKAGE / 'examples' / name, self.source)

    def test_good_export_uses_distinct_orders_not_lines(self):
        report = run(self.root, self.config, self.now)
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['metrics']['line_count'], 6)
        self.assertEqual(report['metrics']['distinct_order_count'], 5)
        self.assertEqual(report['metrics']['total_recorded_line_value_eur'], 720)
        self.assertEqual(report['metrics']['mean_order_value_eur'], 144)
        self.assertTrue((Path(report['run_directory']) / 'report.html').exists())
        self.assertEqual(len(report['management']['applied_copy_changes']), 1)

    def test_dirty_export_stops_before_analysis(self):
        self.example('dirty_orders.csv')
        before = self.source.read_bytes()
        report = run(self.root, self.config, self.now)
        trace = json.loads((Path(report['run_directory']) / 'trace.json').read_text())
        self.assertEqual(report['status'], 'blocked_data_quality')
        self.assertNotIn('analysis', trace)
        self.assertNotIn('metrics', report)
        self.assertEqual(report['management']['rows_before'], 7)
        self.assertEqual(report['management']['rows_after'], 6)
        self.assertEqual(before, self.source.read_bytes())

    def test_source_snapshot_matches_original(self):
        before = self.source.read_bytes()
        report = run(self.root, self.config, self.now)
        self.assertEqual((Path(report['run_directory']) / 'source.csv').read_bytes(), before)
        self.assertEqual(self.source.read_bytes(), before)

    def test_missing_input_still_produces_error_report(self):
        self.source.unlink()
        report = run(self.root, self.config, self.now)
        self.assertEqual(report['status'], 'input_error')
        self.assertTrue((Path(report['run_directory']) / 'report.json').exists())
        self.assertNotIn('metrics', report)

    def test_bad_headers_block_ingestion(self):
        for payload in (b'x,y\n1,2\n', b'order_id,order_id\na,b\n'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                read_export(payload)

    def test_invalid_numeric_text_is_not_guessed(self):
        self.source.write_text(self.source.read_text().replace('100.00', '100,00'))
        report = run(self.root, self.config, self.now)
        self.assertEqual(report['status'], 'input_error')

    def test_non_finite_number_blocks_business_metrics(self):
        self.source.write_text(self.source.read_text().replace('100.00', '1' + '0' * 400))
        report = run(self.root, self.config, self.now)
        self.assertEqual(report['status'], 'blocked_data_quality')
        self.assertNotIn('metrics', report)

    def test_no_automatic_operations_when_policy_is_empty(self):
        self.config['automatic_copy_operations'] = []
        report = run(self.root, self.config, self.now)
        self.assertEqual(report['management']['applied_copy_changes'], [])

    def test_repeated_run_has_separate_audit_and_no_same_day_baseline(self):
        first = run(self.root, self.config, self.now)
        second = run(self.root, self.config, self.now)
        self.assertNotEqual(first['run_id'], second['run_id'])
        self.assertNotIn('previous_run_id', second['snapshot_comparison'])

    def test_previous_day_baseline_triggers_threshold_alert(self):
        first = run(self.root, self.config, self.now)
        text = self.source.read_text().replace('100.00', '500.00')
        self.source.write_text(text)
        second = run(self.root, self.config, self.now + timedelta(days=1))
        self.assertEqual(second['snapshot_comparison']['previous_run_id'], first['run_id'])
        self.assertIn('snapshot_change', [i['id'] for i in second['issues']])

    def test_optional_model_failure_does_not_prevent_reporting(self):
        self.config['use_local_llm_for_priority'] = True
        self.example('dirty_orders.csv')
        with patch('model_client.chat', side_effect=ValueError('offline')):
            report = run(self.root, self.config, self.now)
        self.assertIn('llm_priority_error', report)
        self.assertTrue((Path(report['run_directory']) / 'report.html').exists())

    def test_html_escapes_client_text(self):
        self.config['client_name'] = '<script>alert(1)</script>'
        report = run(self.root, self.config, self.now)
        page = (Path(report['run_directory']) / 'report.html').read_text()
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)

    def test_fractional_or_negative_quantities_block(self):
        for quantity in ('0.5', '-1'):
            with self.subTest(quantity=quantity):
                self.example('clean_orders.csv')
                self.source.write_text(self.source.read_text().replace(',2,100.00,', ',' + quantity + ',100.00,'))
                report = run(self.root, self.config, self.now)
                self.assertEqual(report['status'], 'blocked_data_quality')

    def test_large_line_value_is_flagged_as_descriptive_outlier(self):
        header = 'order_id,line_id,order_date,quantity,line_value_eur,marketing_cost_eur\n'
        values = [10, 11, 12, 13, 14, 15, 16, 1000]
        content = header + ''.join(
            f'O{index},1,2026-11-19,1,{value},{index + 1}\n'
            for index, value in enumerate(values)
        )
        self.source.write_text(content)
        report = run(self.root, self.config, self.now)
        self.assertEqual(report['status'], 'completed')
        flagged = [item for item in report['issues'] if item['id'] == 'line_value_outliers']
        self.assertEqual(flagged[0]['rows'], [8])

    def test_calendar_schedule_is_eight_am(self):
        job = job_definition('/tmp/a project', '/tmp/a project/.venv/bin/python')
        self.assertEqual(job['StartCalendarInterval'], {'Hour': 8, 'Minute': 0})
        self.assertEqual(job['ProgramArguments'], ['/tmp/a project/.venv/bin/python', '-m', 'daily_analytics'])
        self.assertNotIn('RunAtLoad', job)


if __name__ == '__main__':
    unittest.main()
