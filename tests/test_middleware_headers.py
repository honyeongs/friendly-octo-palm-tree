"""Early ASGI rejections must receive the same headers as routed responses."""
import asyncio
import unittest

from netsec.monitor.middleware import GuardMiddleware


class MiddlewareHeaderTests(unittest.TestCase):
    def probe(self, headers, body=b'', proxies=(), client=('127.0.0.1', 1234)):
        async def run():
            messages = []
            async def app(scope, receive, send):
                await send({'type': 'http.response.start', 'status': 200, 'headers': []})
                await send({'type': 'http.response.body', 'body': b'OK'})
            async def receive():
                return {'type': 'http.request', 'body': body, 'more_body': False}
            async def send(message):
                messages.append(message)
            await GuardMiddleware(app, proxies)({'type': 'http', 'method': 'POST',
                'headers': headers, 'client': client}, receive, send)
            response = next(item for item in messages if item['type'] == 'http.response.start')
            return response['status'], dict(response['headers'])
        return asyncio.run(run())

    def test_all_rejection_paths_and_normal_response_have_headers(self):
        for headers, body, proxies, expected in (
            ([(b'content-encoding', b'gzip')], b'', (), 415),
            ([], b'x' * (1024 * 1024 + 1), (), 413),
            ([(b'x-real-ip', b'invalid')], b'', ('127.0.0.1/32',), 400),
            ([], b'', (), 200),
        ):
            with self.subTest(status=expected):
                status, result = self.probe(headers, body, proxies)
                self.assertEqual(status, expected)
                self.assertEqual(result[b'cache-control'], b'no-store')
                self.assertEqual(result[b'x-frame-options'], b'DENY')
                self.assertEqual(result[b'x-content-type-options'], b'nosniff')
                self.assertEqual(result[b'referrer-policy'], b'no-referrer')
                self.assertIn(b"frame-ancestors 'none'", result[b'content-security-policy'])
