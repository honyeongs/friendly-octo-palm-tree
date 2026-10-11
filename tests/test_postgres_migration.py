"""Real PostgreSQL migration and pg_dump/pg_restore checks in CI."""

import os
import tempfile
import unittest
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


@unittest.skipUnless(os.getenv('NETSEC_TEST_POSTGRES'), 'A dedicated PostgreSQL instance is required')
class MigrationTests(unittest.TestCase):
    def test_migrate_backup_restore_and_reject_nonempty_destination(self):
        import psycopg
        from psycopg import sql
        from netsec.monitor.accounts import create_organization
        from netsec.monitor.database import Database
        from netsec.monitor.schemas import Setup
        from netsec.monitor.maintenance import backup
        from netsec.saas.migration import migrate, restore_check
        base = os.environ['NETSEC_TEST_POSTGRES']
        parsed = urlsplit(base)
        databases = ['netsec_migration_' + uuid.uuid4().hex, 'netsec_restore_' + uuid.uuid4().hex]
        try:
            with psycopg.connect(base, autocommit=True) as conn:
                for name in databases:
                    conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            target_dsn, scratch_dsn = [urlunsplit(parsed._replace(path='/' + name)) for name in databases]
            with tempfile.TemporaryDirectory() as folder:
                old = Database(Path(folder) / 'old.sqlite3')
                with old.connect(write=True) as conn:
                    create_organization(conn, Setup(organization='Migration', display_name='Admin', email='migration@example.test', password='Synthetic migration password'))
                snapshot = backup(old, Path(folder) / 'snapshot.sqlite3')
                target = Database(target_dsn)
                counts = migrate(snapshot, target)
                self.assertEqual(counts['organizations'], 1)
                with self.assertRaises(ValueError):
                    migrate(snapshot, target)
                archive = backup(target, Path(folder) / 'backup.dump')
                restored = restore_check(target, archive, scratch_dsn)
                self.assertEqual(restored['organizations'], 1)
                self.assertEqual(restored['users'], 1)
                with self.assertRaises(ValueError):
                    restore_check(target, archive, target_dsn)
        finally:
            with psycopg.connect(base, autocommit=True) as conn:
                for name in databases:
                    conn.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))
