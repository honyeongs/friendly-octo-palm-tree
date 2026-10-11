"""Provider signatures, SSO browser binding and network boundary tests."""

import hashlib
import hmac
import json
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

from tests import test_saas as fixtures
from netsec.monitor.security import digest, token
from netsec.monitor.database import now


class ProviderTests(fixtures.SaasTests):
    # Only provider-focused methods here; inherited SaaS contracts run in their own class.
    def test_webhook_signature_and_replay_reconciles_current_state(self):
        from netsec.saas.billing import reconcile
        config = replace(self.settings.saas, billing_mode='stripe', stripe_key='sk_test_placeholder', stripe_webhook_secret='whsec_placeholder', prices={'team': 'price_team'})
        self.app.state.settings = replace(self.settings, saas=config)
        with self.app.state.db.connect(write=True) as conn:
            conn.execute("UPDATE subscriptions SET customer_id='cus_alpha',provider='stripe' WHERE org_id=?", (self.org,))
            conn.execute("INSERT INTO billing_requests(id,org_id,plan,created_at) VALUES('request',?,'team',?)", (self.org, now()))
        event = {'id': 'evt_signed', 'livemode': False, 'type': 'customer.subscription.updated', 'data': {'object': {'id': 'sub_alpha', 'status': 'active'}}}
        current = {'id': 'sub_alpha', 'customer': 'cus_alpha', 'status': 'past_due', 'metadata': {'netsec_request': 'request'},
                   'items': {'data': [{'price': {'id': 'price_team'}, 'quantity': 1, 'current_period_end': int(time.time()) + 86400}]}}
        client = Mock(); client.v1.subscriptions.retrieve.return_value = current
        raw = json.dumps(event).encode(); stamp = str(int(time.time()))
        signature = hmac.new(config.stripe_webhook_secret.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
        self.assertEqual(self.client.post('/api/saas/billing/webhook', content=raw, headers={'Stripe-Signature': 't=' + stamp + ',v1=bad'}).status_code, 400)
        with patch('netsec.saas.billing.provider', return_value=client):
            result = self.client.post('/api/saas/billing/webhook', content=raw, headers={'Stripe-Signature': 't=' + stamp + ',v1=' + signature})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertTrue(self.client.post('/api/saas/billing/webhook', content=raw, headers={'Stripe-Signature': 't=' + stamp + ',v1=' + signature}).json()['duplicate'])
        self.assertEqual(self.client.get('/api/saas/billing').json()['subscription']['status'], 'past_due')
        self.assertEqual(client.v1.subscriptions.retrieve.call_count, 1)
        event['id'], event['livemode'] = 'evt_live', True
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            reconcile(self.app.state.db, self.app.state.settings, event, client)

    def sso_transaction(self, claims, cookie=True):
        state, browser, nonce = token(), token(), token()
        issuer = 'https://id.example.test'
        value = {'oidc_issuer': issuer, 'oidc_client_id': 'client', 'oidc_require_mfa': True}
        with self.app.state.db.connect(write=True) as conn:
            conn.execute('INSERT INTO tenant_integrations VALUES(?,?,?) ON CONFLICT(org_id) DO UPDATE SET encrypted_config=excluded.encrypted_config', (self.org, self.app.state.vault.seal(self.org, value), now()))
            conn.execute('INSERT INTO oidc_transactions VALUES(?,?,?,?,?)', (digest(state), self.org, digest(browser), self.app.state.vault.seal(self.org, {'issuer': issuer, 'nonce': nonce, 'code_verifier': token()}), (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(timespec='microseconds')))
        if cookie:
            self.client.cookies.set('netsec_oidc', browser)
        result = {'iss': issuer, 'sub': 'subject-alpha', 'email': 'admin@alpha.test', 'email_verified': True, 'nonce': nonce, 'amr': ['pwd', 'otp'], **claims}
        remote = Mock(); remote.fetch_access_token = AsyncMock(return_value={'id_token': 'verified-by-provider-library'})
        remote.parse_id_token = AsyncMock(return_value=result)
        return state, remote

    def test_sso_missing_cookie_and_nonce_cannot_login(self):
        state, remote = self.sso_transaction({}, cookie=False)
        with patch('netsec.saas.oidc.remote', return_value=remote):
            self.assertEqual(self.client.get('/api/saas/sso/callback', params={'state': state, 'code': 'code'}).status_code, 400)
            self.assertEqual(remote.fetch_access_token.call_count, 0)
        state, remote = self.sso_transaction({'nonce': 'wrong'})
        with patch('netsec.saas.oidc.remote', return_value=remote):
            self.assertEqual(self.client.get('/api/saas/sso/callback', params={'state': state, 'code': 'code'}).status_code, 403)

    def test_sso_replay_mfa_and_verified_membership(self):
        for claims in ({'email_verified': False}, {'amr': ['hwk']}, {'email': 'outsider@example.test'}, {'iss': 'https://evil.test'}):
            state, remote = self.sso_transaction(claims)
            with patch('netsec.saas.oidc.remote', return_value=remote):
                self.assertEqual(self.client.get('/api/saas/sso/callback', params={'state': state, 'code': 'code'}).status_code, 403)
        state, remote = self.sso_transaction({})
        with patch('netsec.saas.oidc.remote', return_value=remote):
            result = self.client.get('/api/saas/sso/callback', params={'state': state, 'code': 'code'}, follow_redirects=False)
            self.assertEqual(result.status_code, 303, result.text)
            self.assertEqual(self.client.get('/api/saas/sso/callback', params={'state': state, 'code': 'code'}).status_code, 400)
        self.assertEqual(self.client.get('/api/me').status_code, 200)

    def test_public_dns_must_not_resolve_private_and_pins_address(self):
        from netsec.saas.network import destination, post_json
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaises(ValueError):
                destination('https://approved.test/hook', ('approved.test',))
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 443))]), patch('netsec.saas.network.PinnedHTTPS') as connection:
            connection.return_value.getresponse.return_value.status = 302
            with self.assertRaises(OSError):
                post_json('https://approved.test/hook', ('approved.test',), {'safe': True})
            connection.assert_called_once_with('approved.test', '8.8.8.8')

    def test_forged_proxy_headers_are_ignored(self):
        from netsec.monitor.middleware import GuardMiddleware
        import asyncio
        seen = []
        async def app(scope, receive, send):
            seen.append(scope['client'][0])
        async def receive():
            return {'type': 'http.request', 'body': b''}
        async def send(message):
            pass
        middleware = GuardMiddleware(app, ('10.0.0.4/32',))
        scope = {'type': 'http', 'method': 'GET', 'client': ('203.0.113.1', 1234), 'headers': [(b'x-real-ip', b'192.0.2.50')]}
        asyncio.run(middleware(scope, receive, send))
        asyncio.run(middleware({**scope, 'client': ('10.0.0.4', 1234)}, receive, send))
        self.assertEqual(seen, ['203.0.113.1', '192.0.2.50'])


# Inheritance supplies fixtures only; avoid re-running the base contract suite twice.
for name in list(fixtures.SaasTests.__dict__):
    if name.startswith('test_') and name not in ProviderTests.__dict__:
        setattr(ProviderTests, name, None)
