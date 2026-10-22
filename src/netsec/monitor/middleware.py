"""Bound request buffering and apply response security headers to errors too."""

from starlette.responses import JSONResponse
import ipaddress


class GuardMiddleware:
    def __init__(self, app, trusted_proxies=()):
        self.app = app
        self.trusted_proxies = [ipaddress.ip_network(value) for value in trusted_proxies]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def secure_send(message):
            if message["type"] == "http.response.start":
                result = list(message.get("headers", []))
                result += [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                           (b"referrer-policy", b"no-referrer"), (b"cache-control", b"no-store"),
                           (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]
                message = {**message, "headers": result}
            await send(message)

        headers = dict(scope["headers"])
        if self.trusted_proxies and scope.get('client'):
            try:
                peer = ipaddress.ip_address(scope['client'][0])
                if any(peer in network for network in self.trusted_proxies) and b'x-real-ip' in headers:
                    address = str(ipaddress.ip_address(headers[b'x-real-ip'].decode('ascii')))
                    scope = {**scope, 'client': (address, scope['client'][1])}
            except (ValueError, UnicodeError):
                return await JSONResponse({'detail': 'Invalid trusted proxy address'}, status_code=400)(scope, receive, secure_send)
        maximum = 1024 * 1024
        if headers.get(b"content-encoding", b"identity") != b"identity":
            return await JSONResponse({"detail": "압축 요청은 지원하지 않습니다."}, status_code=415)(scope, receive, secure_send)
        chunks, size = [], 0
        if scope["method"] not in ("GET", "HEAD", "OPTIONS"):
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                size += len(message.get("body", b""))
                if size > maximum:
                    return await JSONResponse({"detail": "요청은 1MB 이하여야 합니다."}, status_code=413)(scope, receive, secure_send)
                chunks.append(message)
                if not message.get("more_body", False):
                    break
        index = 0

        async def replay():
            nonlocal index
            if index < len(chunks):
                result = chunks[index]
                index += 1
                return result
            return await receive()

        await self.app(scope, replay, secure_send)
