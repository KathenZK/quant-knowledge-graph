"""Bounded opt-in citation checks. Never follow local-network redirects or log URLs."""
from contextlib import closing
import http.client
import ipaddress
import json
from pathlib import Path
import socket
import sqlite3
import ssl
import threading
import time
from urllib.parse import urljoin, urlsplit

from quantgraph.graph.personal_catalog import personal_url


def public_destination(url):
    parts = urlsplit(url)
    if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password:
        raise ValueError('Unsafe citation URL')
    port = parts.port or (443 if parts.scheme == 'https' else 80)
    if port not in {80, 443}:
        raise ValueError('Nonstandard citation port')
    addresses = sorted({r[4][0] for r in socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(addr).is_global for addr in addresses):
        raise ValueError('Private network addresses are not citation destinations')
    return parts, port, addresses[0]


def head(url):
    """Pin the vetted address for this connection, including TLS SNI and Host."""
    parts, port, address = public_destination(url)
    connection = http.client.HTTPConnection(address, port, timeout=3)
    if parts.scheme == 'https':
        raw = socket.create_connection((address, port), timeout=3)
        try:
            connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parts.hostname)
        except Exception:
            raw.close()
            raise
    with closing(connection):
        target = parts.path or '/'
        if parts.query:
            target += '?' + parts.query
        connection.request('HEAD', target, headers={'Host': parts.netloc,
            'User-Agent': 'QuantGraph-Citation-Check/1.0', 'Accept': '*/*'})
        response = connection.getresponse()
        return response.status, response.getheader('Location')


class SourceLinks:
    def __init__(self, path, *, requester=head, clock=time.time):
        self.path, self.requester, self.clock = Path(path), requester, clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock, self.last_request = threading.Lock(), 0
        with sqlite3.connect(self.path) as con:
            con.execute('CREATE TABLE IF NOT EXISTS citation_checks(url TEXT PRIMARY KEY, checked REAL, payload TEXT)')
        self.path.chmod(0o600)

    def read(self, url):
        url = personal_url(url)
        if not url:
            return dict(status='NO_URL', message='来源没有可安全打开的链接；本机资料仍保留。')
        with sqlite3.connect(self.path) as con:
            row = con.execute('SELECT checked,payload FROM citation_checks WHERE url=?', (url,)).fetchone()
        if row:
            return json.loads(row[1]) | dict(cached=True, stale=self.clock()-row[0] > 86400)
        return dict(status='UNCHECKED', message='尚未检查外链；不会因链接失效删除知识条目。')

    def check(self, url):
        url = personal_url(url)
        existing = self.read(url)
        if existing['status'] == 'NO_URL' or (existing.get('cached') and not existing.get('stale')):
            return existing
        with self.lock:
            if self.clock() - self.last_request < 1:
                return dict(status='RATE_LIMITED', message='检查过于频繁，请稍后再试。')
            self.last_request = self.clock()
            target, code = url, None
            try:
                for _ in range(3):
                    code, location = self.requester(target)
                    if code in {301, 302, 303, 307, 308} and location:
                        target = personal_url(urljoin(target, location))
                        if not target:
                            raise ValueError('Unsafe redirect')
                        continue
                    break
                if 200 <= code < 300:
                    status, message = 'AVAILABLE', '本次检查可访问；正文和许可仍以来源为准。'
                elif code in {401, 403, 429, 405}:
                    status, message = 'RESTRICTED', '来源限制自动检查或需要访问权限；可自行打开核对，未绕过限制。'
                elif code in {404, 410}:
                    status, message = 'MISSING', '来源返回不存在或已移除；本机已收录资料仍保留。'
                else:
                    status, message = 'UNVERIFIED', '本次未能确认链接有效；不能据此断定资料不存在。'
            except (OSError, ValueError, http.client.HTTPException):
                status, message = 'UNREACHABLE', '本次连接未成功或地址不适合检查；资料仍保留，可稍后核对。'
            value = dict(status=status, message=message, http_status=code, checked_at=self.clock(), cached=False)
            with sqlite3.connect(self.path) as con:
                con.execute('INSERT OR REPLACE INTO citation_checks VALUES (?,?,?)',
                            (url, self.clock(), json.dumps(value, ensure_ascii=False)))
            return value
