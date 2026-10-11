"""Explainable multi-account, distributed and privilege-change correlations."""

from collections import defaultdict, deque
from datetime import datetime, timedelta


def evidence(row):
    return {key: row[key] for key in ('id', 'timestamp', 'host', 'source_ip', 'username', 'outcome', 'method')}


def candidates(org, rows):
    result = []
    failures = [row for row in rows if row['event_type'] == 'auth.login' and row['outcome'] == 'failure']
    for rule, grouped_key, distinct_key, title in (
            ('password_spraying', 'source_ip', 'username', '여러 계정 대상 인증 실패'),
            ('distributed_failures', 'username', 'source_ip', '여러 IP의 동일 계정 인증 실패')):
        groups = defaultdict(deque)
        for row in failures:
            group = groups[(row['host'], row[grouped_key])]
            cutoff = datetime.fromisoformat(row['timestamp']) - timedelta(seconds=org['window_seconds'])
            while group and datetime.fromisoformat(group[0]['timestamp']) < cutoff:
                group.popleft()
            group.append(row)
            if len({item[distinct_key] for item in group}) >= org['threshold']:
                result.append((rule, 'medium', row['host'], row['source_ip'] if grouped_key == 'source_ip' else '',
                               row['username'] if grouped_key == 'username' else '', title, [evidence(item) for item in group]))
    by_account = defaultdict(list)
    for row in rows:
        key = (row['host'], row['username'], row['source_ip'])
        if row['event_type'] == 'auth.login':
            by_account[key].append(row)
        if row['event_type'] == 'role.change' and row['outcome'] == 'success':
            lower = datetime.fromisoformat(row['timestamp']) - timedelta(seconds=org['success_seconds'])
            logins = [item for item in by_account[key] if datetime.fromisoformat(item['timestamp']) >= lower]
            successes = [item for item in logins if item['outcome'] == 'success']
            if successes:
                last_success = successes[-1]
                failed = [item for item in logins if item['outcome'] == 'failure' and item['timestamp'] <= last_success['timestamp']]
                severity = 'high' if len(failed) >= org['threshold'] else 'medium'
                result.append(('privilege_change_after_login', severity, row['host'], row['source_ip'], row['username'],
                               '인증 성공 후 권한 변경', [evidence(item) for item in (*failed, last_success, row)]))
    return result
