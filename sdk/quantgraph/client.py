"""HTTP SDK; no database copying and no runner endpoints."""
import gzip
import json
import os
from pathlib import Path
from urllib.parse import quote, urlsplit
import requests


class QuantGraphClient:
    def __init__(self, base_url, token=None, *, timeout=60, session=None):
        url = urlsplit(base_url)
        if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password:
            raise ValueError('Invalid QuantGraph URL')
        if url.scheme != 'https' and url.hostname not in {'localhost', '127.0.0.1', '::1'}:
            raise ValueError('Remote connections require HTTPS')
        self.base_url, self.timeout = base_url.rstrip('/'), timeout
        self.token = token or os.getenv('QUANTGRAPH_TOKEN')
        self.session = session or requests.Session()

    def _request(self, method, path, **kwargs):
        headers = kwargs.pop('headers', {})
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        response = self.session.request(method, self.base_url + path, headers=headers,
                                        timeout=self.timeout, allow_redirects=False, **kwargs)
        if 300 <= response.status_code < 400:
            raise ValueError('Redirect refused; configure the canonical API URL')
        response.raise_for_status()
        return response.json()

    def ingest_batch(self, batch, *, compress=False):
        if compress:
            raw = json.dumps(batch, ensure_ascii=False, allow_nan=False).encode()
            return self._request('POST', '/v1/ingest/grokbot/batches', data=gzip.compress(raw),
                                 headers={'Content-Type': 'application/json', 'Content-Encoding': 'gzip'})
        return self._request('POST', '/v1/ingest/grokbot/batches', json=batch)

    def get_job(self, job_id):
        return self._request('GET', '/v1/ingest/jobs/' + quote(job_id, safe=''))

    def get_batch(self, batch_id):
        return self._request('GET', '/v1/ingest/batches/' + quote(batch_id, safe=''))

    def search_factors(self, query=None, **filters):
        return self._request('GET', '/v1/factors', params={'q': query, **filters})['items']

    def get_factor(self, factor_id):
        return self._request('GET', '/v1/factors/' + quote(factor_id, safe=''))

    def get_strategy_concepts(self, **page):
        return self._request('GET', '/v1/research/strategies/concepts', params=page)['items']

    def get_strategy_templates(self, **page):
        return self._request('GET', '/v1/research/strategies/templates', params=page)['items']

    def get_strategy_variants(self, **page):
        return self._request('GET', '/v1/research/strategies/variants', params=page)['items']

    def find_strategies_by_factor(self, factor_id, **page):
        return self._request('GET', '/v1/research/factors/' + quote(factor_id, safe='') + '/strategies', params=page)['items']

    def export_research_candidates(self, **page):
        return self._request('GET', '/v1/research/candidates', params=page)

    def research_assessments(self):
        return self._request('GET', '/v1/research/assessments')

    def research_evidence(self, variant_id):
        return self._request('GET', '/v1/research/evidence/' + quote(variant_id, safe=''))

    def research_chain(self, variant_id):
        return self._request('GET', '/v1/research/chain/' + quote(variant_id, safe=''))

    def submit_research_evidence(self, evidence):
        return self._request('POST', '/v1/research/evidence', json=evidence)

    def submit_factor_study(self, result):
        return self._request('POST', '/v1/research/factor-studies', json=result)

    def factor_studies(self, entity_id, *, profile='commercial', **page):
        if profile not in {'research', 'commercial'}:
            raise ValueError('Invalid profile')
        path = ('/v1/research/factor-studies/' + quote(entity_id, safe='') if profile == 'research'
                else '/v1/factors/' + quote(entity_id, safe='') + '/studies')
        return self._request('GET', path, params=page)


def load_batch(path, *, batch_id=None, collector_version=None):
    path = Path(path)
    raw = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
    suffix = Path(path.stem).suffix if path.suffix == '.gz' else path.suffix
    if suffix in {'.jsonl', '.ndjson'}:
        if not batch_id or not collector_version:
            raise ValueError('JSONL requires --batch-id and --collector-version')
        return {'batch_id': batch_id, 'collector_version': collector_version,
                'records': [json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()]}
    return json.loads(raw)
