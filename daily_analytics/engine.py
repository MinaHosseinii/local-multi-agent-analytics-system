import csv
import hashlib
import html
import io
import json
import math
import re
import uuid
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import TypedDict
from zoneinfo import ZoneInfo

from langgraph.graph import StateGraph, START, END
from cleaning_proposal import propose_cleaning
from cleaning_storage import encode_values
from data_tools import calculate_correlation
from quality_report import build_quality_report

REQUIRED = {'order_id', 'line_id', 'order_date', 'quantity',
            'line_value_eur', 'marketing_cost_eur'}
NUMERIC = {'quantity', 'line_value_eur', 'marketing_cost_eur'}
SAFE_OPERATIONS = {'remove_exact_duplicate', 'normalize_date'}
DECIMAL = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)')
INTEGER = re.compile(r'[1-9][0-9]*')


class RunState(TypedDict, total=False):
    config: dict
    root: str
    report: dict
    rows: list
    proposal: dict
    candidate: list


def number(value):
    # Explicit CSV ingestion contract, not a model-selected repair.
    if value == '':
        return None
    if DECIMAL.fullmatch(value):
        return float(value)
    return value  # Validation flags other text; never guess decimal commas.


def read_export(payload):
    reader = csv.DictReader(io.StringIO(payload.decode('utf-8-sig')))
    fields = reader.fieldnames
    if fields is None or len(fields) != len(set(fields)):
        raise ValueError('CSV has absent or duplicate headers.')
    if not REQUIRED.issubset(fields):
        raise ValueError('Missing required columns: ' + ', '.join(sorted(REQUIRED - set(fields))))
    rows = []
    for raw in reader:
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError('CSV row has a different number of fields than its header.')
        row = dict(raw)
        row['order_id'] = raw['order_id'] if raw['order_id'] != '' else None
        line = raw['line_id']
        row['line_id'] = int(line) if INTEGER.fullmatch(line) else line
        for column in NUMERIC:
            row[column] = number(raw[column])
        rows.append(row)
    return rows


def save_json(path, value):
    path = Path(path)
    text = json.dumps(encode_values(value), ensure_ascii=False, indent=2, allow_nan=False)
    with path.open('x', encoding='utf-8') as handle:
        handle.write(text)


def issue(report, code, message, severity='warning', **extra):
    report['issues'].append({'id': code, 'severity': severity, 'message': message, **extra})


def load_node(state):
    report = state['report']
    path = Path(state['root']) / state['config']['input_csv']
    try:
        # Read once; subsequent stages work on this exact snapshot.
        with path.open('rb') as handle:
            import os
            before = os.fstat(handle.fileno())
            payload = handle.read()
            after = os.fstat(handle.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Input changed during reading; export it atomically and retry.')
        rows = read_export(payload)
        report['source'] = {
            'path': str(path.resolve()), 'sha256': hashlib.sha256(payload).hexdigest(),
            'bytes': len(payload), 'row_count': len(rows),
            'modified_at': datetime.fromtimestamp(after.st_mtime, ZoneInfo(state['config']['timezone'])).isoformat(),
        }
        age_hours = (datetime.fromisoformat(report['started_at']).timestamp() - after.st_mtime) / 3600
        if age_hours > state['config']['stale_export_hours']:
            issue(report, 'stale_export', 'Export file is older than the configured freshness limit.', age_hours=round(age_hours, 1))
        # Preserve original bytes in the run folder; never modify the input file.
        with (Path(report['run_directory']) / 'source.csv').open('xb') as handle:
            handle.write(payload)
        return {'rows': rows, 'report': report}
    except (OSError, UnicodeError, ValueError, csv.Error, OverflowError) as error:
        report['status'] = 'input_error'
        issue(report, 'input_error', str(error), 'error')
        return {'report': report}


def prepare_node(state):
    report = state['report']
    report['original_quality'] = build_quality_report(state['rows'])
    proposal = propose_cleaning(state['rows'])
    allowed = set(state['config']['automatic_copy_operations'])
    if not allowed.issubset(SAFE_OPERATIONS):
        raise ValueError('Unknown automatic-copy policy operation.')
    selected = [c for c in proposal['changes'] if c['operation'] in allowed]
    # Rebuild from original snapshot, applying only enabled policy operations.
    removed = {c['source_row'] for c in selected if c['operation'] == 'remove_exact_duplicate'}
    dates = {c['source_row']: c['after'] for c in selected if c['operation'] == 'normalize_date'}
    import copy
    candidate, mapping = [], []
    for index, row in enumerate(state['rows'], 1):
        if index in removed:
            continue
        item = copy.deepcopy(row)
        if index in dates:
            item['order_date'] = dates[index]
        candidate.append(item)
        mapping.append(index)
    report['management'] = {
        'policy': sorted(allowed), 'applied_copy_changes': selected,
        'rows_before': len(state['rows']), 'rows_after': len(candidate),
        'source_row_numbers': mapping, 'source_overwritten': False,
    }
    save_json(Path(report['run_directory']) / 'candidate.json', candidate)
    return {'candidate': candidate, 'report': report}


def quality_node(state):
    report, rows = state['report'], state['candidate']
    quality = build_quality_report(rows)
    report['candidate_quality'] = quality
    if not rows:
        issue(report, 'empty_dataset', 'No data rows were supplied.', 'error')
    if quality['keys']['invalid_keys']:
        issue(report, 'invalid_keys', 'Invalid order-line keys need review.', 'error', rows=quality['keys']['invalid_keys'])
    if quality['keys']['repeated_keys']:
        issue(report, 'key_conflicts', 'Repeated or conflicting order-line keys remain.', 'error', groups=quality['keys']['repeated_keys'])
    if quality['dates']['invalid_count'] or quality['dates']['missing_count']:
        issue(report, 'invalid_dates', 'Invalid or missing dates need review.', 'error')
    for column, findings in quality['numeric_columns'].items():
        if findings['invalid_count'] or findings['missing_count']:
            issue(report, 'numeric_' + column, f'Invalid or missing {column} values need review.', 'error')
    for index, row in enumerate(rows, 1):
        quantity = row['quantity']
        if isinstance(quantity, (int, float)) and not isinstance(quantity, bool):
            if not math.isfinite(quantity) or quantity <= 0 or quantity != int(quantity):
                issue(report, f'quantity_{index}', 'Quantity must be a positive integer under this sales-only policy.', 'error', row=index)
        for column in ('line_value_eur', 'marketing_cost_eur'):
            value = row[column]
            if isinstance(value, (int, float)) and math.isfinite(value) and value < 0:
                issue(report, f'negative_{column}_{index}', f'Negative {column} requires a separate returns/refunds policy.', 'error', row=index)
    # An order cannot silently span dates in this export contract.
    order_dates = {}
    for row in rows:
        if isinstance(row['order_id'], str):
            order_dates.setdefault(row['order_id'], set()).add(str(row['order_date']))
    if any(len(dates) != 1 for dates in order_dates.values()):
        issue(report, 'order_date_conflict', 'An order ID has inconsistent order dates.', 'error')
    if any(item['severity'] == 'error' for item in report['issues']):
        report['status'] = 'blocked_data_quality'
    else:
        report['status'] = 'ready'
    return {'report': report}


def analyse_node(state):
    report, rows = state['report'], state['candidate']
    order_totals, daily_totals = {}, {}
    values = []
    for row in rows:
        value = row['line_value_eur']
        values.append(value)
        order_totals.setdefault(row['order_id'], []).append(value)
        daily_totals.setdefault(row['order_date'], []).append(value)
    totals = {key: math.fsum(items) for key, items in order_totals.items()}
    dates = {key: math.fsum(items) for key, items in sorted(daily_totals.items())}
    metrics = {
        'line_count': len(rows), 'distinct_order_count': len(totals),
        'total_recorded_line_value_eur': math.fsum(values),
        'mean_line_value_eur': mean(values), 'median_line_value_eur': median(values),
        'mean_order_value_eur': mean(totals.values()),
        'daily_totals_eur': dates,
        'date_range': [min(dates), max(dates)],
    }
    if not all(math.isfinite(metrics[key]) for key in (
        'total_recorded_line_value_eur', 'mean_line_value_eur', 'median_line_value_eur', 'mean_order_value_eur'
    )):
        raise ValueError('Numerical overflow in aggregate metrics.')
    report['metrics'] = metrics
    # Descriptive outlier flag only: this is not a hypothesis test or a cause.
    if len(values) >= 8:
        centre = median(values)
        mad = median([abs(value - centre) for value in values])
        if mad > 0:
            unusual = [index for index, value in enumerate(values, 1)
                       if 0.67448975 * abs(value - centre) / mad > 3.5]
            if unusual:
                issue(report, 'line_value_outliers', 'Unusual line values under the median/MAD rule; inspect records before drawing conclusions.', rows=unusual)
    report['correlations'] = [calculate_correlation(
        rows, 'marketing_cost_eur', 'line_value_eur', method
    ) for method in state['config']['correlation_methods']]
    report['correlation_scope'] = 'Order lines, descriptive association only; repeated orders may create dependent observations. No p-values or causal claims.'
    report['status'] = 'completed'
    return {'report': report}


def compare_node(state):
    report = state['report']
    if report['status'] != 'completed':
        return {'report': report}
    root = Path(state['root'])
    previous = []
    for path in (root / state['config']['output_directory']).glob('*/report.json'):
        try:
            item = json.loads(path.read_text(encoding='utf-8'))
            if (item.get('status') == 'completed'
                and item.get('business_date', '') < report['business_date']
                and item.get('source', {}).get('path') == report['source']['path']
                and item.get('config_fingerprint') == report['config_fingerprint']):
                previous.append(item)
        except (ValueError, OSError):
            continue
    if previous:
        baseline = max(previous, key=lambda item: item['started_at'])
        old = baseline['metrics']['total_recorded_line_value_eur']
        new = report['metrics']['total_recorded_line_value_eur']
        change = None if old == 0 else (new - old) / abs(old) * 100
        report['snapshot_comparison'] = {
            'previous_run_id': baseline['run_id'], 'previous_business_date': baseline['business_date'],
            'total_export_value_change_percent': change,
            'interpretation': 'Change between complete export snapshots, not automatically daily sales growth.',
        }
        if change is not None and abs(change) >= state['config']['total_value_change_alert_percent']:
            issue(report, 'snapshot_change', 'Total export value changed beyond the configured threshold.', change_percent=round(change, 2))
    else:
        report['snapshot_comparison'] = {'message': 'No earlier comparable successful daily snapshot. Trend alert not calculated.'}
    return {'report': report}


def narrative_node(state):
    report = state['report']
    # The LLM can prioritise existing issue IDs, not invent business facts.
    if state['config'].get('use_local_llm_for_priority') and report['issues']:
        try:
            from model_client import chat
            response = chat([
                {'role': 'system', 'content': 'Prioritize up to three supplied issue IDs. Return only {"issue_ids":["id"]}. Never add IDs.'},
                {'role': 'user', 'content': json.dumps(report['issues'], ensure_ascii=False)},
            ])
            choice = json.loads(response)
            ids = choice.get('issue_ids') if isinstance(choice, dict) else None
            allowed = {item['id'] for item in report['issues']}
            if (set(choice) != {'issue_ids'} or not isinstance(ids, list)
                or len(ids) > 3 or any(not isinstance(item, str) for item in ids)
                or len(set(ids)) != len(ids) or not set(ids).issubset(allowed)):
                raise ValueError('Model returned invalid issue IDs.')
            report['llm_priority'] = ids
        except Exception as error:
            # Optional model assistance must not suppress the evidence report.
            report['llm_priority_error'] = f'{type(error).__name__}: {error}'
    return {'report': report}


def write_report(report):
    directory = Path(report['run_directory'])
    lines = [f"# {report['client_name']} — daily analytics", '',
             f"Status: **{report['status']}**", f"Run: {report['run_id']}",
             f"Time: {report['started_at']}", '', '## Findings', '']
    if report['issues']:
        lines += [f"- [{item['severity']}] {item['message']}" for item in report['issues']]
    else:
        lines += ['No blocking quality issues found by the implemented rules.']
    if report.get('management'):
        m = report['management']
        lines += ['', '## Managed copy', '', f"Rows: {m['rows_before']} → {m['rows_after']}. Original file was not overwritten.",
                  f"Applied changes: {len(m['applied_copy_changes'])}."]
    if report.get('metrics'):
        m = report['metrics']
        lines += ['', '## Export KPIs', '',
                  f"- Order lines: {m['line_count']}", f"- Distinct orders: {m['distinct_order_count']}",
                  f"- Total recorded line value: EUR {m['total_recorded_line_value_eur']:.2f}",
                  f"- Mean order value: EUR {m['mean_order_value_eur']:.2f}",
                  f"- Data dates: {m['date_range'][0]} through {m['date_range'][1]}",
                  '', 'These metrics describe this export, not necessarily yesterday’s business.']
        lines += ['', '## Descriptive correlations', '']
        for c in report['correlations']:
            lines += [f"- {c['method']}: {c['coefficient']:.4f} ({c['pairs_used']} pairs)" if c.get('ok') else f"- {c['method']}: unavailable ({c.get('reason', c.get('error'))})"]
        lines += ['', report['correlation_scope']]
    else:
        lines += ['', 'Business KPIs and correlations were not published because the input or required quality checks failed.']
    lines += ['', '## Next action', '',
              'Review flagged source rows, correct the upstream export, and run again. Never guess conflicting IDs or ambiguous dates.' if report['status'] != 'completed'
              else 'Review warnings and snapshot changes; investigate the underlying business records before drawing conclusions.']
    text = '\n'.join(lines) + '\n'
    (directory / 'report.md').write_text(text, encoding='utf-8')
    # Escape source-derived text; this page contains no generated executable code.
    chart = ''
    dates = report.get('metrics', {}).get('daily_totals_eur', {})
    if dates:
        maximum = max(dates.values()) or 1
        chart = '<h2>Recorded line value by date</h2>' + ''.join(
            f'<p>{html.escape(date)} — EUR {value:.2f}<br><meter min="0" max="{maximum}" value="{value}" style="width:100%"></meter></p>'
            for date, value in dates.items())
    page = ('<!doctype html><html><meta charset="utf-8"><title>Daily analytics</title>'
            '<style>body{font:16px system-ui;max-width:950px;margin:40px auto;padding:20px;background:#f5f7fb;color:#182a3b}pre{white-space:pre-wrap;line-height:1.6}meter{height:24px}</style>'
            '<body><pre>' + html.escape(text) + '</pre>' + chart + '</body></html>')
    (directory / 'report.html').write_text(page, encoding='utf-8')
    save_json(directory / 'report.json', report)


def report_node(state):
    write_report(state['report'])
    return {'report': state['report']}


def build_graph():
    builder = StateGraph(RunState)
    for name, node in [('ingest', load_node), ('manage_copy', prepare_node),
                       ('quality', quality_node), ('analysis', analyse_node),
                       ('compare', compare_node), ('priority', narrative_node), ('report', report_node)]:
        builder.add_node(name, node)
    builder.add_edge(START, 'ingest')
    builder.add_conditional_edges('ingest', lambda s: 'report' if s['report']['status'] == 'input_error' else 'manage_copy')
    builder.add_edge('manage_copy', 'quality')
    builder.add_conditional_edges('quality', lambda s: 'analysis' if s['report']['status'] == 'ready' else 'priority')
    builder.add_edge('analysis', 'compare')
    builder.add_edge('compare', 'priority')
    builder.add_edge('priority', 'report')
    builder.add_edge('report', END)
    return builder.compile()


def run(root, config, now=None):
    root = Path(root).resolve()
    now = now or datetime.now(ZoneInfo(config['timezone']))
    if now.tzinfo is None:
        raise ValueError('Run timestamp must include a timezone.')
    now = now.astimezone(ZoneInfo(config['timezone']))
    run_id = now.strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:12]
    directory = root / config['output_directory'] / run_id
    directory.mkdir(parents=True, exist_ok=False)
    report = {
        'run_id': run_id, 'client_name': config['client_name'], 'status': 'started',
        'started_at': now.isoformat(), 'business_date': now.date().isoformat(),
        'run_directory': str(directory), 'issues': [],
        'config_fingerprint': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        'automatic_policy': 'Configured reversible copy operations only; no source writes, no guessed corrections, no imputation.',
    }
    trace = []
    try:
        for update in build_graph().stream({'config': config, 'root': str(root), 'report': report}, stream_mode='updates'):
            for node, values in update.items():
                trace.append(node)
                if 'report' in values:
                    report = values['report']
        # Persist trace after graph report is committed.
        save_json(directory / 'trace.json', trace)
        return report
    except Exception as error:
        report['status'] = 'run_error'
        report.pop('metrics', None)
        report.pop('correlations', None)
        issue(report, 'run_error', f'{type(error).__name__}: {error}', 'error')
        if not (directory / 'report.json').exists():
            write_report(report)
        if not (directory / 'trace.json').exists():
            save_json(directory / 'trace.json', trace)
        raise
