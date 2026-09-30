import copy
import json
import pytest
from quantgraph.graph.site_feedback import FeedbackLedger,digest,read_envelope
SOURCE='https://synthetic.chatgpt.site'
def event(seq=1,note='继续核对'):
    target=dict(kind='strategy',entity_id='test:one',entity_type='StrategyVariant',definition_revision='v1')
    payload=dict(starred=False,status='值得研究',tags=['来源'],group='',note=note,summary='',questions='',reason='',aliases=[],problem='')
    return dict(seq=seq,event_id=str(seq),owner_id='synthetic-owner',target_key=digest(target),record_revision=seq,target=target,payload=payload,payload_sha256=digest(dict(target=target,payload=payload)),mutation_id='test-'+str(seq),created_at='2026-09-30T00:00:00Z')
def batch(*events,after=0):return dict(schema_version='quantgraph-feedback/v1',after_cursor=after,next_cursor=events[-1]['seq'] if events else after,has_more=False,events=list(events))
def test_append_replay_restart_and_immutability(tmp_path):
    path=tmp_path/'feedback.sqlite';ledger=FeedbackLedger(path);r=ledger.ingest(SOURCE,batch(event()));assert r['inserted']==1
    assert ledger.ingest(SOURCE,batch(event()))['replayed']==1
    again=FeedbackLedger(path);assert again.cursor(SOURCE)==1;assert again.events(SOURCE)[0]['payload']['note']=='继续核对'
    with pytest.raises(Exception),again.connect() as c:c.execute('DELETE FROM site_feedback_events')
    with pytest.raises(ValueError,match='changed'):ledger.ingest(SOURCE,batch(event(note='不同内容')))
    assert ledger.cursor(SOURCE)==1

def test_bad_later_row_is_atomic_and_gap_rejected(tmp_path):
    ledger=FeedbackLedger(tmp_path/'f.sqlite');wrong=event(2);wrong['payload_sha256']='a'*64
    with pytest.raises(ValueError):ledger.ingest(SOURCE,batch(event(),wrong))
    assert ledger.cursor(SOURCE)==0 and ledger.events(SOURCE)==[]
    with pytest.raises(ValueError):ledger.ingest(SOURCE,batch(event(2),after=1))
    with pytest.raises(ValueError):ledger.ingest(SOURCE,batch(event(999999999999)))
    assert ledger.ingest(SOURCE,batch(event(),event(2)))['durable_cursor']==2
    assert ledger.ingest(SOURCE,batch(event(2),event(3),after=1))['inserted']==1

def test_source_and_strict_json_validation(tmp_path):
    p=tmp_path/'x.json';p.write_text('{"a":1,"a":2}')
    with pytest.raises(ValueError):read_envelope(p)
    p.write_text('{"a":NaN}')
    with pytest.raises(ValueError):read_envelope(p)
    for url in ['http://synthetic.chatgpt.site','https://x:y@synthetic.chatgpt.site','https://synthetic.chatgpt.site/?token=x','']:
        with pytest.raises(ValueError):FeedbackLedger.source(url)
    ledger=FeedbackLedger(tmp_path/'f.sqlite');x=copy.deepcopy(event());x['target']['origin_run_id']='run'
    with pytest.raises(ValueError):ledger.ingest(SOURCE,batch(x))
