"""Operator-only snapshot migration, PostgreSQL backup and restore verification."""

import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qs

from netsec.monitor.database import Database

TABLES = ('organizations', 'users', 'sessions', 'sources', 'events', 'incidents', 'comments', 'exclusions', 'audit',
          'outbox', 'rate_limits', 'subscriptions', 'usage_months', 'action_tokens', 'verified_users', 'mail_jobs',
          'tenant_integrations', 'billing_requests', 'billing_events', 'incident_tasks', 'service_alerts',
          'privacy_requests', 'oidc_transactions', 'oidc_bindings')


def migrate(source_path, target):
    source = Path(source_path).resolve()
    if target.backend != 'postgres' or not source.is_file():
        raise ValueError('Migration requires a SQLite snapshot and PostgreSQL destination')
    report = {}
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as old, target.connect(write=True) as conn:
        old.execute('BEGIN')
        if old.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or old.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Source integrity check failed')
        for table in TABLES:
            if conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:
                raise ValueError('Destination must be empty; never merge production databases')
        available = {row[0] for row in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in TABLES:
            if table not in available:
                continue
            cursor = old.execute(f'SELECT * FROM {table}')
            fields = [column[0] for column in cursor.description]
            if any(not re.fullmatch('[a-z_]+', field) for field in fields):
                raise ValueError('Invalid source columns')
            names = ','.join('"' + name + '"' for name in fields)
            placeholders = ','.join('?' for _ in fields)
            count = 0
            for values in cursor:
                conn.execute(f'INSERT INTO {table}({names}) VALUES({placeholders})', values)
                count += 1
            report[table] = count
            if conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] != count:
                raise ValueError('Migration count mismatch')
        for table in ('events', 'audit'):
            conn.execute("SELECT setval(pg_get_serial_sequence(?, 'id'), coalesce((SELECT max(id) FROM " + table + "),1), EXISTS(SELECT 1 FROM " + table + '))', (table,))
    return report


def pg_environment(dsn):
    parsed = urlsplit(dsn)
    allowed = {'sslmode': 'PGSSLMODE', 'sslrootcert': 'PGSSLROOTCERT', 'sslcert': 'PGSSLCERT', 'sslkey': 'PGSSLKEY'}
    options = parse_qs(parsed.query, strict_parsing=True)
    if set(options) - set(allowed):
        raise ValueError('Unsupported dump connection option')
    env = os.environ.copy()
    env.update(PGHOST=parsed.hostname or '', PGPORT=str(parsed.port or 5432), PGUSER=unquote(parsed.username or ''),
               PGPASSWORD=unquote(parsed.password or ''), PGDATABASE=unquote(parsed.path.lstrip('/')), PGCONNECT_TIMEOUT='10')
    env.update({allowed[key]: value[0] for key, value in options.items()})
    return env


def pg_backup(db, destination):
    dump, restore = shutil.which('pg_dump'), shutil.which('pg_restore')
    if not dump or not restore:
        raise ValueError('Install compatible PostgreSQL backup tools on the operator host')
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    stream = target.open('xb')
    try:
        with stream:
            result = subprocess.run([dump, '--format=custom', '--no-owner', '--no-acl'], env=pg_environment(db.dsn), stdout=stream, stderr=subprocess.PIPE, timeout=300)
        if result.returncode:
            raise ValueError('pg_dump failed; check operator connectivity without publishing credentials')
        result = subprocess.run([restore, '--list', str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
        if result.returncode:
            raise ValueError('Backup archive validation failed')
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def restore_check(db, archive, scratch_dsn):
    if not scratch_dsn or scratch_dsn == db.dsn:
        raise ValueError('Use a separate empty scratch database, never the active database')
    restore = shutil.which('pg_restore')
    if not restore:
        raise ValueError('Install compatible PostgreSQL restore tools on the operator host')
    import psycopg
    with psycopg.connect(scratch_dsn) as conn:
        if conn.execute("SELECT 1 FROM pg_tables WHERE schemaname='public' LIMIT 1").fetchone():
            raise ValueError('Scratch database must be empty')
    result = subprocess.run([restore, '--no-owner', '--no-acl', '--exit-on-error', '--single-transaction', '--dbname=' + urlsplit(scratch_dsn).path.lstrip('/'), str(archive)],
                            env=pg_environment(scratch_dsn), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
    if result.returncode:
        raise ValueError('Restore verification failed')
    restored = Database(scratch_dsn)
    with restored.connect() as conn:
        return {table: conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in TABLES}
