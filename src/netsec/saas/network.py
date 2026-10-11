"""Public HTTPS delivery with DNS pinning, no redirects and no environment proxy."""

import http.client
import ipaddress
import json
import socket
import ssl
from urllib.parse import urlsplit


def destination(url, allowed_hosts):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.fragment or '\\' in url
            or any(ord(char) <= 32 for char in url)):
        raise ValueError('An HTTPS URL on port 443 is required')
    host = parsed.hostname.encode('idna').decode().lower()
    if host not in allowed_hosts:
        raise ValueError('Destination host is not operator-approved')
    addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError('Private, loopback and reserved destinations are forbidden')
    return parsed, host, addresses[0]


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=10, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def post_json(url, allowed_hosts, payload, headers=None):
    parsed, host, address = destination(url, allowed_hosts)
    conn = PinnedHTTPS(host, address)
    try:
        conn.request('POST', (parsed.path or '/') + ('?' + parsed.query if parsed.query else ''),
                     body=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', **(headers or {})})
        response = conn.getresponse()
        if not 200 <= response.status < 300:
            raise OSError('External delivery rejected')
        response.read(4096)
    finally:
        conn.close()
