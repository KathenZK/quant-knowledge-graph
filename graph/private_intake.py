"""Explicit, hash-pinned import of private source-review cards into the Catalog.

This is a local command, never an HTTP mutation or a source-execution bridge.
Candidates remain private and retain their supplied admission/evidence states.
"""
import argparse
import hashlib
import json
from pathlib import Path

from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.catalog_projection import item
from quantgraph.graph.corpus_research import _read_file, _loads, _finite, _identifier, _sha


def import_cards(catalog, path, expected_sha256, kind):
    content = _read_file(path, limit=8*1024*1024)
    _sha(expected_sha256)
    digest = hashlib.sha256(content).hexdigest()
    if digest != expected_sha256:
        raise ValueError('Card snapshot digest mismatch')
    if kind not in {'factor', 'strategy'}:
        raise ValueError('Unsupported card type')
    rows = _loads(content)
    _finite(rows)
    if isinstance(rows, dict):
        rows = rows.get('records')
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('Expected bounded card array')
    prepared=[];seen=set();overlays=[];guarded_overlays={}
    with catalog.connect() as con:
        existing={}
        exact={r['entity_id']:dict(r) for r in con.execute("SELECT entity_id,kind,definition_revision,payload FROM catalog_items WHERE active=1")}
        for found in con.execute("SELECT entity_id,payload FROM catalog_items WHERE active=1 AND kind='strategy'"):
            for native_id in json.loads(found['payload']).get('source_native_ids',[]):
                existing.setdefault(native_id,[]).append(found['entity_id'])
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Card must be an object')
        for key in ['record_id','definition_id','definition_version','stable_id','native_source_id','version_id']:
            if row.get(key) is not None:
                _identifier(row[key])
        for key in ['relation','validation','timing','code_evidence','primary_paper','field_evidence','worked_example','novelty']:
            if row.get(key) is not None and not isinstance(row[key],dict):
                raise ValueError('Card field must be an object: '+key)
        for key in ['name_zh','name','one_line','formula','formula_plain_zh','source_url','original_rule_text','sign_interpretation','admission_status']:
            if row.get(key) is not None and (not isinstance(row[key],str) or len(row[key])>100000):
                raise ValueError('Card text field invalid: '+key)
        for key in ['required_data','blocked_reasons','strategy_uses_zh']:
            if key in row and (not isinstance(row[key],list) or len(row[key])>1000 or not all(isinstance(x,str) for x in row[key])):
                raise ValueError('Card list field invalid: '+key)
        if any(not isinstance(v,dict) for v in (row.get('field_evidence') or {}).values()):
            raise ValueError('Field evidence entries must be objects')
        native = row.get('record_id') or row.get('definition_id')
        name = row.get('name_zh') or row.get('name')
        if not isinstance(native,str) or not native or not isinstance(name,str) or not name or len(name)>500:
            raise ValueError('Stable source identity and name required')
        if native in seen:
            raise ValueError('Duplicate card identity in snapshot')
        seen.add(native)
        eid='private-intake:'+kind+':'+hashlib.sha256(native.encode()).hexdigest()[:32]
        revision=hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        relation=row.get('relation') or {}
        if relation.get('binding_mode') and (relation.get('type')!='source_curation_overlay_for' or relation['binding_mode']!='EXACT_CURRENT_REVISION'):
            raise ValueError('Unsupported metadata overlay binding mode')
        if relation.get('type')=='source_curation_overlay_for' and relation.get('binding_mode')=='EXACT_CURRENT_REVISION':
            target=exact.get(relation.get('expected_entity_id'))
            revision_pin=relation.get('expected_definition_revision')
            allowed_kinds={'strategy'} if kind=='strategy' else {'factor','source'}
            if (not target or target['kind'] not in allowed_kinds or not isinstance(revision_pin,str)
                    or not revision_pin or target['definition_revision']!=revision_pin
                    or native!=relation.get('id')
                    or row.get('entity_type')!=kind or row.get('native_source_id')!=native
                    or native not in json.loads(target['payload']).get('source_native_ids',[])):
                raise ValueError('Metadata overlay requires exact current entity, native ID, type and revision')
            guarded_overlays[target['entity_id']]=(revision_pin, target['kind'], native)
            overlays.append((target['entity_id'],revision,row))
            continue
        if kind=='strategy' and relation.get('type')=='source_curation_overlay_for' and relation.get('also_in_frozen_5813') is True:
            matches=existing.get(relation.get('id'),[])
            if len(matches)!=1:
                raise ValueError('Source review overlay needs exactly one existing native record')
            overlays.append((matches[0],revision,row))
            continue
        actual_kind='factor' if kind=='factor' or row.get('entity_type')=='signal_component' else 'strategy'
        label={'development_fixture':'开发样例 · ','research_model':'研究模型 · ','signal_component':'规则组件 · '}.get(row.get('entity_type'),'')
        status=row.get('admission_status') or (row.get('validation') or {}).get('definition_status') or 'PENDING_REVIEW'
        value=item('strategy' if actual_kind=='strategy' else 'source',eid,label+name,'StrategySourceCandidate' if actual_kind=='strategy' else 'FactorSourceRecord',revision,
            visibility='PRIVATE',source_type='COLLECTION_CANDIDATE' if actual_kind=='strategy' else 'factor_source_record',
            source_name='已采集策略资料' if actual_kind=='strategy' else '因子与信号资料',
            source_native_ids=[row.get('native_source_id') or native],source_url=row.get('source_url'),
            source_locator=row.get('source_locator'),source_revision=row.get('source_revision') or (row.get('code_evidence') or {}).get('commit'),
            source_sha256=row.get('source_sha256') or (row.get('code_evidence') or {}).get('sha256'),
            description=row.get('one_line') or row.get('original_rule_text'),formula=row.get('formula'),
            required_fields=row.get('required_data',[]),frequency=(row.get('timing') or {}).get('frequency'),
            result_status='unresearched',intake_status=str(status),intake_record_id=native,
            statuses=dict(catalog='已收录资料 · '+str(status),implementation='未由导入证明',readiness='按逐项状态核对',result='未由导入生成研究结果',display='PRIVATE'))
        if actual_kind=='strategy':
            rule=row.get('original_rule_text')
            raw={'raw_record':{'规则':rule,'名称':name,'source_url':row.get('source_url'),'市场':row.get('market')},'variant':{'original_rule_text':rule,'source_native_id':native,'source_url_raw':row.get('source_url')},'intake_card':row}
        else:
            raw={'formula':row.get('formula'),'raw_definition':row.get('formula_plain_zh'),'required_fields':row.get('required_data',[]),'source_url':row.get('source_url'),'source_native_id':row.get('native_source_id') or native,'intake_card':row}
        prepared.append((value,raw))
    inserted=updated=noop=review_inserted=review_noop=0
    with catalog.lock,catalog.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        for eid,(pin,expected_kind,native) in guarded_overlays.items():
            current=con.execute('SELECT definition_revision,kind,payload FROM catalog_items WHERE entity_id=? AND active=1',(eid,)).fetchone()
            if (not current or current[0]!=pin or current[1]!=expected_kind
                    or native not in json.loads(current[2]).get('source_native_ids',[])):
                raise ValueError('Catalog revision changed before metadata overlay import')
        con.execute('CREATE TABLE IF NOT EXISTS private_intake_reviews (sequence INTEGER PRIMARY KEY, entity_id TEXT NOT NULL, revision TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(entity_id,revision))')
        for eid,revision,row in overlays:
            cursor=con.execute('INSERT OR IGNORE INTO private_intake_reviews(entity_id,revision,payload) VALUES (?,?,?)',(eid,revision,json.dumps(row,ensure_ascii=False,sort_keys=True)))
            if cursor.rowcount:review_inserted+=1
            else:review_noop+=1
        for value,raw in prepared:
            old=con.execute('SELECT definition_revision FROM catalog_items WHERE entity_id=?',(value['entity_id'],)).fetchone()
            if old and old[0]==value['definition_revision']:
                noop+=1
                continue
            if old:updated+=1
            else:inserted+=1
            catalog._put(con,value,'private-intake:'+kind,raw)
            con.execute("UPDATE catalog_items SET visibility='PRIVATE' WHERE entity_id=?",(value['entity_id'],))
    return {'input_sha256':digest,'records':len(prepared)+len(overlays),'new_catalog_entries':inserted,'updated_entries':updated,'unchanged_entries':noop,'inserted_reviews':review_inserted,'unchanged_reviews':review_noop,'existing_record_reviews':len(overlays),'kind':kind,'entity_ids':[v['entity_id'] for v,_ in prepared]+[eid for eid,_,_ in overlays],
            'visibility':'PRIVATE','admission_upgraded':False,'research_results_created':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--kind',choices=['factor','strategy'],required=True)
    args=parser.parse_args()
    print(json.dumps(import_cards(CatalogRepository(args.catalog),args.input,args.sha256,args.kind),ensure_ascii=False))

if __name__=='__main__':
    main()
