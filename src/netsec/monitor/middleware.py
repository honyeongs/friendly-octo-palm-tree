"""Bound request buffering and apply response security headers to errors too."""

from starlette.responses import JSONResponse


class GuardMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        maximum = 1024 * 1024
        if headers.get(b"content-encoding", b"identity") != b"identity":
            return await JSONResponse({"detail": "압축 요청은 지원하지 않습니다."}, status_code=415)(scope, receive, send)
        chunks, size = [], 0
        if scope["method"] not in ("GET", "HEAD", "OPTIONS"):
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                size += len(message.get("body", b""))
                if size > maximum:
                    return await JSONResponse({"detail": "요청은 1MB 이하여야 합니다."}, status_code=413)(scope, receive, send)
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

        async def secure_send(message):
            if message["type"] == "http.response.start":
                result = list(message.get("headers", []))
                result += [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                           (b"referrer-policy", b"no-referrer"), (b"cache-control", b"no-store"),
                           (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]
                message = {**message, "headers": result}
            await send(message)

        await self.app(scope, replay, secure_send)
