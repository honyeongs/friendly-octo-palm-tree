"""Commercial contracts and adversarial regressions on SQLite and PostgreSQL."""

import json
import os
import re
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock

from fastapi.testclient import TestClient
from netsec.monitor.app import create_app
from netsec.monitor.config import Settings
from netsec.monitor.database import now
from netsec.saas.config import ServiceSettings

PASSWORD = 'test password not a credential'


class SaasTests(unittest.TestCase):
    postgres = False

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db_path = Path(self.temp.name) / 'saas.sqlite3'
        if self.postgres:
            import psycopg
            from psycopg import sql
            from urllib.parse import urlsplit, urlunsplit
            import uuid
            self.base_dsn = os.environ['NETSEC_TEST_POSTGRES']
            self.database_name = 'netsec_test_' + uuid.uuid4().hex
            with psycopg.connect(self.base_dsn, autocommit=True) as conn:
                conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.database_name)))
            parsed = urlsplit(self.base_dsn)
            db_path = urlunsplit(parsed._replace(path='/' + self.database_name))
        from cryptography.fernet import Fernet
        service = ServiceSettings(enabled=True, encryption_key=Fernet.generate_key().decode())
        self.settings = Settings(database=db_path, origin='http://testserver', saas=service)
        self.app = create_app(self.settings, run_worker=False)
        self.client = TestClient(self.app)
        self.client.headers['Origin'] = self.settings.origin
        self.org = self.signup('Alpha', 'admin@alpha.test')
        self.login(self.client, self.org, 'admin@alpha.test')

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()
        if self.postgres:
            import psycopg
            from psycopg import sql
            with psycopg.connect(self.base_dsn, autocommit=True) as conn:
                conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(self.database_name)))

    def latest_token(self, email):
        with self.app.state.db.connect() as conn:
            row = conn.execute('SELECT * FROM mail_jobs WHERE recipient=? ORDER BY created_at DESC LIMIT 1', (email,)).fetchone()
        body = self.app.state.vault.open(row['org_id'], row['encrypted_body'])
        return re.search(r'#action/([\w-]+)', body)[1], row

    def signup(self, name, email):
        # Reset only the test fixture's per-IP throttle to allow multiple synthetic tenants.
        with self.app.state.db.connect(write=True) as conn:
            conn.execute("DELETE FROM rate_limits WHERE key LIKE 'signup-ip:%'")
        result = self.client.post('/api/saas/signup', json={'organization': name, 'display_name': name, 'email': email,
            'password': PASSWORD, 'accepted_terms': True, 'terms_version': 'draft-1'})
        self.assertEqual(result.status_code, 202, result.text)
        token, _ = self.latest_token(email)
        result = self.client.post('/api/saas/consume', json={'token': token})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()['org_id']

    def login(self, client, org, email, password=PASSWORD):
        result = client.post('/api/login', json={'org_id': org, 'email': email, 'password': password})
        self.assertEqual(result.status_code, 200, result.text)
        client.headers['X-CSRF-Token'] = result.json()['csrf']
        return result.json()

    def source(self):
        result = self.client.post('/api/sources', json={'name': 'App', 'kind': 'app'})
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    def events(self, count=6):
        clock = datetime.now(timezone.utc) - timedelta(seconds=90)
        return [{'event_id': 'e' + str(i), 'timestamp': (clock + timedelta(seconds=i * 5)).isoformat(),
                 'source_ip': '192.0.2.1', 'username': 'alice', 'host': 'app', 'event_type': 'auth.login',
                 'outcome': 'success' if i == 5 else 'failure'} for i in range(count)]

    def send(self, source, events):
        return self.client.post('/api/v1/events', headers={'Authorization': 'Bearer ' + source['token']}, json={'events': events})

    def test_signup_verification_single_use_and_no_plaintext(self):
        token, row = self.latest_token('admin@alpha.test')
        self.assertNotIn(token, row['encrypted_body'])
        self.assertEqual(self.client.post('/api/saas/consume', json={'token': token}).status_code, 400)
        self.assertEqual(self.client.get('/api/saas/billing').json()['subscription']['status'], 'trialing')
        self.assertEqual(self.client.post('/api/setup', json={'organization': 'x', 'email': 'x@b.test', 'display_name': 'x', 'password': PASSWORD}).status_code, 403)

    def test_unverified_cannot_login_and_terms_required(self):
        payload = {'organization': 'Pending', 'display_name': 'P', 'email': 'pending@example.test', 'password': PASSWORD, 'accepted_terms': False, 'terms_version': 'draft-1'}
        self.assertEqual(self.client.post('/api/saas/signup', json=payload).status_code, 422)
        payload['accepted_terms'] = True
        self.assertEqual(self.client.post('/api/saas/signup', json=payload).status_code, 202)
        _, row = self.latest_token(payload['email'])
        result = self.client.post('/api/login', json={'org_id': row['org_id'], 'email': payload['email'], 'password': PASSWORD})
        self.assertEqual(result.status_code, 401)

    def test_invite_role_and_reserved_seats(self):
        for i in range(4):
            result = self.client.post('/api/saas/invites', json={'email': f'invite{i}@example.test', 'role': 'viewer'})
            self.assertEqual(result.status_code, 202, result.text)
        self.assertEqual(self.client.post('/api/saas/invites', json={'email': 'extra@example.test'}).status_code, 402)
        token, _ = self.latest_token('invite0@example.test')
        result = self.client.post('/api/saas/consume', json={'token': token, 'display_name': 'Viewer', 'password': PASSWORD})
        self.assertEqual(result.status_code, 200, result.text)
        viewer = TestClient(self.app); self.addCleanup(viewer.close); viewer.headers['Origin'] = self.settings.origin
        self.login(viewer, self.org, 'invite0@example.test')
        for route in ('billing', 'integrations', 'privacy'):
            self.assertEqual(viewer.get('/api/saas/' + route).status_code, 403)
        self.assertEqual(viewer.post('/api/saas/invites', json={'email': 'evil@example.test', 'role': 'admin'}).status_code, 403)
        self.assertEqual(self.client.post('/api/users', json={'email': 'bypass@example.test', 'display_name': 'x', 'password': PASSWORD}).status_code, 409)

    def test_password_reset_generic_and_session_revocation(self):
        messages = []
        for email in ('admin@alpha.test', 'missing@alpha.test'):
            result = self.client.post('/api/saas/email', json={'org_id': self.org, 'email': email})
            messages.append((result.status_code, result.json()))
        self.assertEqual(messages[0], messages[1])
        token, _ = self.latest_token('admin@alpha.test')
        result = self.client.post('/api/saas/consume', json={'token': token, 'password': PASSWORD + ' new'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get('/api/me').status_code, 401)
        self.login(self.client, self.org, 'admin@alpha.test', PASSWORD + ' new')

    def test_expired_token_and_secret_validation_redaction(self):
        self.client.post('/api/saas/email', json={'org_id': self.org, 'email': 'admin@alpha.test'})
        token, _ = self.latest_token('admin@alpha.test')
        with self.app.state.db.connect(write=True) as conn:
            conn.execute("UPDATE action_tokens SET expires_at='2000-01-01T00:00:00.000000+00:00'")
        self.assertEqual(self.client.post('/api/saas/consume', json={'token': token, 'password': PASSWORD}).status_code, 400)
        result = self.client.post('/api/saas/consume', json={'token': token, 'password': 'sensitive' * 100})
        self.assertNotIn('sensitive', result.text)

    def test_password_change_revokes_pending_recovery(self):
        self.client.post('/api/saas/email', json={'org_id': self.org, 'email': 'admin@alpha.test'})
        recovery, _ = self.latest_token('admin@alpha.test')
        changed = self.client.post('/api/password', json={'current_password': PASSWORD, 'new_password': PASSWORD + ' changed'})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.client.get('/api/me').status_code, 401)
        result = self.client.post('/api/saas/consume', json={'token': recovery, 'password': PASSWORD + ' stolen'})
        self.assertEqual(result.status_code, 400)
        self.login(self.client, self.org, 'admin@alpha.test', PASSWORD + ' changed')

    def test_sensitive_actions_share_reauthentication_throttle(self):
        for i in range(10):
            path = '/api/saas/privacy' if i % 2 else '/api/saas/billing/cancel'
            result = self.client.post(path, json={'password': 'incorrect', **({'kind': 'delete'} if i % 2 else {})})
            self.assertEqual(result.status_code, 403, result.text)
        result = self.client.post('/api/saas/privacy/export', json={'kind': 'export', 'password': PASSWORD})
        self.assertEqual(result.status_code, 429)

    def test_quota_atomic_replay_and_conflict(self):
        source = self.source(); events = self.events()
        self.assertEqual(self.send(source, events).status_code, 202)
        self.assertEqual(self.client.get('/api/saas/billing').json()['usage']['events'], 6)
        with self.app.state.db.connect(write=True) as conn:
            conn.execute('UPDATE usage_months SET events=100000 WHERE org_id=?', (self.org,))
        self.assertEqual(self.send(source, events).json()['duplicates'], 6)
        result = self.send(source, [{**events[0], 'event_id': 'new'}])
        self.assertEqual(result.status_code, 402)
        self.assertEqual(self.client.get('/api/events').json()['total'], 6)
        self.assertEqual(self.send(source, [{**events[0], 'username': 'changed'}]).status_code, 409)

    def test_subscription_expiry_keeps_read_access(self):
        source = self.source()
        with self.app.state.db.connect(write=True) as conn:
            conn.execute("UPDATE subscriptions SET period_end='2000-01-01' WHERE org_id=?", (self.org,))
        self.assertEqual(self.send(source, self.events()).status_code, 402)
        self.assertEqual(self.client.get('/api/incidents').status_code, 200)

    def test_mock_purchase_reauth_and_cancel(self):
        self.assertEqual(self.client.post('/api/saas/billing/checkout', json={'plan': 'team', 'password': 'wrong'}).status_code, 403)
        result = self.client.post('/api/saas/billing/checkout', json={'plan': 'team', 'password': PASSWORD})
        self.assertEqual(result.status_code, 200, result.text)
        request_id = result.json()['request_id']
        self.assertEqual(self.client.get('/api/saas/billing').json()['subscription']['plan'], 'starter')
        body = {'request_id': request_id, 'password': PASSWORD}
        self.assertEqual(self.client.post('/api/saas/billing/mock-confirm', json=body).json()['charged'], False)
        self.assertEqual(self.client.post('/api/saas/billing/mock-confirm', json=body).status_code, 409)
        self.assertEqual(self.client.get('/api/saas/billing').json()['subscription']['plan'], 'team')
        self.assertEqual(self.client.post('/api/saas/billing/cancel', json={'password': PASSWORD}).status_code, 200)
        self.assertEqual(self.client.get('/api/saas/billing').json()['subscription']['cancel_at_end'], 1)

    def test_new_tenant_cannot_access_purchase_secrets_or_privacy(self):
        source = self.source(); self.send(source, self.events())
        incident = self.client.get('/api/incidents').json()['items'][0]
        purchase = self.client.post('/api/saas/billing/checkout', json={'plan': 'team', 'password': PASSWORD}).json()['request_id']
        beta = self.signup('Beta', 'admin@beta.test')
        other = TestClient(self.app); self.addCleanup(other.close); other.headers['Origin'] = self.settings.origin
        self.login(other, beta, 'admin@beta.test')
        self.assertEqual(other.post('/api/saas/billing/mock-confirm', json={'request_id': purchase, 'password': PASSWORD}).status_code, 409)
        result = other.put('/api/saas/incidents/' + incident['id'] + '/task', json={'version': incident['version'], 'due_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
        self.assertEqual(result.status_code, 404)
        export = other.post('/api/saas/privacy/export', json={'password': PASSWORD, 'kind': 'export'}).json()
        self.assertEqual(export['data']['events'], [])
        self.assertNotIn('password_hash', json.dumps(export))

    def test_integrations_encrypt_bound_secrets_and_redact(self):
        result = self.client.put('/api/saas/integrations', json={'password': PASSWORD, 'webhook_token': 'private-secret'})
        self.assertEqual(result.status_code, 200, result.text)
        read = self.client.get('/api/saas/integrations')
        self.assertNotIn('private-secret', read.text)
        self.assertTrue(read.json()['webhook_token_set'])
        with self.app.state.db.connect() as conn:
            sealed = conn.execute('SELECT encrypted_config FROM tenant_integrations WHERE org_id=?', (self.org,)).fetchone()[0]
        self.assertNotIn('private-secret', sealed)
        with self.assertRaises(ValueError):
            self.app.state.vault.open('different-org', sealed)

    def test_ssrf_and_sso_lockout_controls(self):
        for url in ('http://127.0.0.1', 'https://127.0.0.1', 'https://169.254.169.254', 'https://example.test@127.0.0.1', 'https://example.test:8443'):
            self.assertEqual(self.client.put('/api/saas/integrations', json={'password': PASSWORD, 'webhook_url': url}).status_code, 422)
        with self.app.state.db.connect(write=True) as conn:
            conn.execute("DELETE FROM rate_limits WHERE key LIKE 'integrations:%'")
        self.assertEqual(self.client.put('/api/saas/integrations', json={'password': PASSWORD, 'oidc_issuer': 'https://evil.test'}).status_code, 422)
        self.assertEqual(self.client.put('/api/saas/integrations', json={'password': PASSWORD, 'sso_required': True}).status_code, 422)
        self.assertEqual(self.client.get('/api/saas/sso/callback?state=forged&code=fake').status_code, 400)

    def test_collection_stale_and_incident_deadline(self):
        from netsec.saas.operations import housekeeping
        from netsec.monitor.notifications import dispatch_one
        source = self.source(); self.send(source, self.events())
        incident = self.client.get('/api/incidents').json()['items'][0]
        while dispatch_one(self.app.state.db, self.settings, vault=self.app.state.vault):
            pass
        result = self.client.put('/api/saas/incidents/' + incident['id'] + '/task', json={'version': incident['version'], 'due_at': (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat(), 'ticket_ref': 'SEC-42'})
        self.assertEqual(result.status_code, 200, result.text)
        with self.app.state.db.connect(write=True) as conn:
            conn.execute("UPDATE sources SET last_seen='2000-01-01' WHERE id=?", (source['id'],))
        housekeeping(self.app.state.db, self.settings)
        health = self.client.get('/api/saas/health').json()
        self.assertEqual(health['items'][0]['status'], 'stale')
        self.assertEqual({row['kind'] for row in health['alerts']}, {'collection', 'deadline'})
        self.assertEqual(health['tasks'][0]['reminders'], 1)

    def test_extended_detection_and_cross_batch(self):
        source = self.source(); events = self.events()
        spray = [{**event, 'event_id': 'spray' + str(i), 'username': 'user' + str(i), 'outcome': 'failure'} for i, event in enumerate(events[:5])]
        self.assertEqual(self.send(source, spray[:3]).status_code, 202)
        self.assertEqual(self.send(source, spray[3:]).status_code, 202)
        self.assertIn('password_spraying', {row['rule'] for row in self.client.get('/api/incidents').json()['items']})
        distributed = [{**event, 'event_id': 'distributed' + str(i), 'source_ip': '192.0.2.' + str(i + 10), 'username': 'target', 'outcome': 'failure'} for i, event in enumerate(events[:5])]
        self.send(source, distributed)
        self.send(source, events)
        role = {**events[-1], 'event_id': 'role', 'event_type': 'role.change', 'timestamp': datetime.now(timezone.utc).isoformat()}
        self.send(source, [role])
        rules = {row['rule']: row for row in self.client.get('/api/incidents').json()['items']}
        self.assertIn('distributed_failures', rules)
        self.assertEqual(rules['privilege_change_after_login']['severity'], 'high')

    def test_deletion_erases_only_requested_tenant(self):
        from netsec.saas.operations import fulfill_delete
        self.send(self.source(), self.events())
        beta = self.signup('Beta', 'admin@beta.test')
        result = self.client.post('/api/saas/privacy', json={'kind': 'delete', 'password': PASSWORD})
        self.assertEqual(result.status_code, 202, result.text)
        removed = fulfill_delete(self.app.state.db, result.json()['id'])
        self.assertEqual(removed['deleted_org_id'], self.org)
        self.assertFalse(removed['backups_removed'])
        self.assertEqual(self.client.get('/api/me').status_code, 401)
        with self.app.state.db.connect() as conn:
            self.assertEqual(conn.execute('SELECT id FROM organizations').fetchone()[0], beta)

    def test_production_refuses_developer_modes(self):
        with self.assertRaises(ValueError):
            replace(self.settings, origin='https://security.example.test').validate()
        with self.assertRaises(ValueError):
            replace(self.settings, saas=replace(self.settings.saas, billing_mode='stripe', stripe_key='sk_live_fake', stripe_webhook_secret='whsec_fake')).validate()


@unittest.skipUnless(os.getenv('NETSEC_TEST_POSTGRES'), 'A dedicated PostgreSQL test instance is required')
class PostgresSaasTests(SaasTests):
    postgres = True
