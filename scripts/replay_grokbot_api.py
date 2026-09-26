"""Private migration of a supplied corpus through the real HTTP SDK.

Run with QUANTGRAPH_TOKEN; outputs aggregate counters only. Source collection
dates absent from the legacy bundle remain unknown; collected_at is explicitly
the migration observation time and is frozen across a replay.
"""
import argparse
from datetime import datetime, timezone
import json

from quantgraph.client import QuantGraphClient
from quantgraph.collectors.grokbot.collector import read_bundle


def batches(bundle, observed_at, size=150):
    for offset in range(0, len(bundle['rows']), size):
        records = []
        for row in bundle['rows'][offset:offset + size]:
            records.append({'record_id': row['id'], 'name': row['名称'], 'author': row.get('作者或机构'),
                'source_url': row['source_url'], 'source_publication_date': row.get('提出日期'),
                'raw_market': row['市场'], 'raw_rule': row['规则'], 'backtestability': row.get('可回测'),
                'collected_at': observed_at,
                'metadata': {'legacy_fields': row, 'legacy_archive_sha256': bundle['sha256'],
                             'collected_at_basis': 'MIGRATION_OBSERVATION_TIME_ORIGINAL_COLLECTION_UNKNOWN'}})
        yield {'batch_id': 'legacy-' + bundle['sha256'][:16] + '-' + str(offset // size),
               'collector_version': 'legacy-corpus-migration-v1', 'records': records}


def replay(client, bundle, observed_at):
    counts = {k: 0 for k in ('accepted', 'duplicate', 'revision', 'curated', 'review_required', 'errors')}
    requests = list(batches(bundle, observed_at))
    for batch in requests:
        result = client.ingest_batch(batch, compress=True)
        for key in counts:
            counts[key] += result[key]
        assert client.get_job(result['job_id'])['status'] == 'COMPLETED'
    replayed = 0
    for batch in requests:
        result = client.ingest_batch(batch, compress=True)
        assert result['accepted'] == result['revision'] == 0
        replayed += result['duplicate']
    return {'input_sha256': bundle['sha256'], 'records': len(bundle['rows']), 'batches': len(requests),
            'first_pass': counts, 'second_pass_duplicates': replayed, 'observed_at': observed_at,
            'transport': 'HTTP+gzip', 'raw_corpus_published': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('archive')
    parser.add_argument('--url', required=True)
    parser.add_argument('--observed-at', default=datetime.now(timezone.utc).isoformat())
    args = parser.parse_args()
    print(json.dumps(replay(QuantGraphClient(args.url), read_bundle(args.archive), args.observed_at), indent=2))
