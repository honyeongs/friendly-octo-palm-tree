"""Failed PostgreSQL backups must not masquerade as usable archives."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from netsec.saas.migration import pg_backup


class BackupFailureTests(unittest.TestCase):
    def test_missing_tools_do_not_create_archive(self):
        with tempfile.TemporaryDirectory() as root, patch('netsec.saas.migration.shutil.which', return_value=None):
            target = Path(root) / 'backup.dump'
            with self.assertRaises(ValueError):
                pg_backup(SimpleNamespace(dsn='postgresql://operator@localhost/db'), target)
            self.assertFalse(target.exists())

    def test_failures_remove_only_new_partial_archives(self):
        with tempfile.TemporaryDirectory() as root, patch('netsec.saas.migration.shutil.which', side_effect=lambda name: '/trusted/' + name):
            target = Path(root) / 'backup.dump'
            db = SimpleNamespace(dsn='postgresql://operator@localhost/db')
            for outcome in (FileNotFoundError('tool disappeared'), subprocess.TimeoutExpired('pg_dump', 300), Mock(returncode=1)):
                kwargs = {'side_effect': outcome} if isinstance(outcome, Exception) else {'return_value': outcome}
                with patch('netsec.saas.migration.subprocess.run', **kwargs), self.assertRaises((OSError, subprocess.TimeoutExpired, ValueError)):
                    pg_backup(db, target)
                self.assertFalse(target.exists())
            target.touch()
            with patch('netsec.saas.migration.subprocess.run') as run, self.assertRaises(FileExistsError):
                pg_backup(db, target)
            run.assert_not_called()
            self.assertTrue(target.exists())

    def test_invalid_archive_is_removed_and_credentials_not_in_arguments(self):
        with tempfile.TemporaryDirectory() as root, patch('netsec.saas.migration.shutil.which', side_effect=lambda name: '/trusted/' + name):
            target = Path(root) / 'backup.dump'
            db = SimpleNamespace(dsn='postgresql://operator:synthetic-test-password@localhost/db')
            with patch('netsec.saas.migration.subprocess.run', side_effect=[Mock(returncode=0), Mock(returncode=1)]) as run, self.assertRaises(ValueError):
                pg_backup(db, target)
            self.assertFalse(target.exists())
            self.assertNotIn('synthetic-test-password', str(run.call_args_list[0].args))
            self.assertEqual(run.call_args_list[0].kwargs['env']['PGPASSWORD'], 'synthetic-test-password')
