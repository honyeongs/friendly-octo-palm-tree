"""Configuration changes must invalidate even SSO callbacks already awaiting the IdP."""
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from netsec.monitor.security import digest, token
from netsec.saas.secrets import integration_snapshot


class SsoRevocationTests(unittest.TestCase):
    postgres = False

    def setUp(self):
        from tests.test_saas_providers import ProviderTests
        self.fixture = ProviderTests()
        self.fixture.postgres = self.postgres
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.client, self.app = self.fixture.client, self.fixture.app

    def change_settings(self, **changes):
        from tests.test_saas import PASSWORD
        response = self.client.put('/api/saas/integrations', json={'password': PASSWORD, **changes})
        self.assertEqual(response.status_code, 200)

    def callback(self, state, remote):
        with patch('netsec.saas.oidc.remote', return_value=remote):
            return self.client.get('/api/saas/sso/callback', params={'state': state, 'code': 'synthetic-code'}, follow_redirects=False)

    def test_inflight_disable_cannot_recreate_session(self):
        state, remote = self.fixture.sso_transaction({})
        claims = remote.parse_id_token.return_value
        async def parse(*args, **kwargs):
            self.change_settings(oidc_issuer='')
            return claims
        remote.parse_id_token.side_effect = parse
        self.assertEqual(self.callback(state, remote).status_code, 400)
        self.assertEqual(self.client.get('/api/me').status_code, 401)
        with self.app.state.db.connect() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT count(*) FROM oidc_bindings').fetchone()[0], 0)

    def test_change_and_restore_still_invalidates_callback(self):
        state, remote = self.fixture.sso_transaction({})
        claims = remote.parse_id_token.return_value
        async def parse(*args, **kwargs):
            from netsec.monitor.database import now
            with self.app.state.db.connect(write=True) as conn:
                original, old_revision = integration_snapshot(conn, self.app.state.vault, self.fixture.org)
                for value in ({**original, 'oidc_require_mfa': False}, original):
                    conn.execute('UPDATE tenant_integrations SET encrypted_config=?,updated_at=? WHERE org_id=?',
                        (self.app.state.vault.seal(self.fixture.org, value), now(), self.fixture.org))
                self.assertNotEqual(integration_snapshot(conn, self.app.state.vault, self.fixture.org)[1], old_revision)
            return claims
        remote.parse_id_token.side_effect = parse
        self.assertEqual(self.callback(state, remote).status_code, 400)
        with self.app.state.db.connect() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM oidc_bindings').fetchone()[0], 0)

    def test_start_rejects_settings_changed_during_discovery(self):
        self.fixture.sso_transaction({})
        remote = Mock()
        async def create(*args, **kwargs):
            self.change_settings(oidc_issuer='')
            return {'url': 'https://id.example.test/authorize', 'state': token()}
        remote.create_authorization_url = AsyncMock(side_effect=create)
        with patch('netsec.saas.oidc.remote', return_value=remote):
            response = self.client.get('/api/saas/sso/start', params={'org_id': self.fixture.org}, follow_redirects=False)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('netsec_oidc=', response.headers.get('set-cookie', ''))
        with self.app.state.db.connect() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM oidc_transactions').fetchone()[0], 0)

    def test_legacy_transaction_fails_closed_before_provider_exchange(self):
        state, remote = self.fixture.sso_transaction({})
        with self.app.state.db.connect(write=True) as conn:
            row = conn.execute('SELECT encrypted_params FROM oidc_transactions WHERE state_hash=?', (digest(state),)).fetchone()
            params = self.app.state.vault.open(self.fixture.org, row[0])
            params.pop('config_revision')
            conn.execute('UPDATE oidc_transactions SET encrypted_params=? WHERE state_hash=?',
                (self.app.state.vault.seal(self.fixture.org, params), digest(state)))
        self.assertEqual(self.callback(state, remote).status_code, 400)
        remote.fetch_access_token.assert_not_called()

    def test_unchanged_configuration_logs_in_once(self):
        state, remote = self.fixture.sso_transaction({})
        self.assertEqual(self.callback(state, remote).status_code, 303)
        self.assertEqual(self.client.get('/api/me').status_code, 200)
        self.assertEqual(self.callback(state, remote).status_code, 400)


@unittest.skipUnless(os.environ.get('NETSEC_TEST_POSTGRES'), 'Dedicated PostgreSQL test service is not configured')
class PostgresSsoRevocationTests(SsoRevocationTests):
    postgres = True
