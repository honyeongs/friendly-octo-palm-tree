"""Exercise real Authlib/JoseRFC signature and OIDC claim validation offline."""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock


class OidcCryptoTests(unittest.TestCase):
    def test_signature_issuer_audience_expiration_nonce(self):
        from authlib.integrations.starlette_client import OAuth
        from joserfc import jwt
        from joserfc.jwk import RSAKey
        key = RSAKey.generate_key(2048)
        client = OAuth().register('test', client_id='netsec-client', issuer='https://issuer.example.test',
                                  id_token_signing_alg_values_supported=['RS256'])
        client.fetch_jwk_set = AsyncMock(return_value={'keys': [key.as_dict(private=False)]})
        claims = {'iss': 'https://issuer.example.test', 'sub': 'subject', 'aud': 'netsec-client',
                  'exp': int(time.time()) + 300, 'iat': int(time.time()), 'nonce': 'nonce-required'}
        def parse(values, signing_key=key):
            encoded = jwt.encode({'alg': 'RS256'}, values, signing_key)
            return asyncio.run(client.parse_id_token({'id_token': encoded}, nonce='nonce-required',
                claims_options={'iss': {'essential': True, 'value': 'https://issuer.example.test'}}, leeway=0))
        self.assertEqual(parse(claims)['sub'], 'subject')
        for changes in ({'iss': 'https://evil.test'}, {'aud': 'other-client'}, {'exp': int(time.time()) - 300}, {'nonce': 'wrong'}):
            with self.subTest(changes=changes), self.assertRaises(Exception):
                parse({**claims, **changes})
        with self.assertRaises(Exception):
            parse(claims, RSAKey.generate_key(2048))
