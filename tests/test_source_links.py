import socket

import pytest

from quantgraph.graph.source_links import SourceLinks, public_destination


def test_private_network_dns_and_scheme_rejected(monkeypatch):
    for address in ['127.0.0.1', '10.0.0.1', '::1', '169.254.169.254']:
        monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: [(2,1,6,'',(address,80))])
        with pytest.raises(ValueError):
            public_destination('https://example.org/article')
    for url in ['file:///private', 'https://user:pass@example.org/', 'http://example.org:22/']:
        with pytest.raises(ValueError):
            public_destination(url)


def test_cache_limits_and_missing_link_never_remove_records(tmp_path):
    calls = []
    def requester(url):
        calls.append(url)
        return 404, None
    links = SourceLinks(tmp_path/'links.sqlite', requester=requester, clock=lambda:1000)
    assert links.read('https://example.org/doc?id=42#methods')['status'] == 'UNCHECKED'
    result = links.check('https://example.org/doc?id=42&token=hidden#methods')
    assert result['status'] == 'MISSING'
    assert calls == ['https://example.org/doc?id=42#methods']
    assert links.check('https://example.org/doc?id=42#methods')['cached']
    assert len(calls) == 1
    assert links.check('https://other.example/')['status'] == 'RATE_LIMITED'


def test_permission_or_timeout_is_not_claimed_dead(tmp_path):
    links = SourceLinks(tmp_path/'restricted.sqlite', requester=lambda url:(403,None))
    assert links.check('https://example.org/')['status'] == 'RESTRICTED'
    def unavailable(url):
        raise TimeoutError()
    links = SourceLinks(tmp_path/'unavailable.sqlite', requester=unavailable)
    assert links.check('https://example.org/')['status'] == 'UNREACHABLE'
