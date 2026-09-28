"""Append a reviewed Lab dataset artifact; the Graph gate computes admission.

No Lab imports, network, strategy computation or status assignment. The input
manifest is a private output of Lab's independent raw reconstruction audit.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from quantgraph.graph.research_gate import evaluate
from quantgraph.models.evidence_v4 import EvidenceEnrichmentV4
from quantgraph.models.market import ResearchContract, canonical_sha256


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_review(previous, contract_path, manifest_path):
    contract_path, manifest_path = Path(contract_path), Path(manifest_path)
    contract_text = contract_path.read_text()
    contract = ResearchContract.model_validate_json(contract_text)
    manifest = json.loads(manifest_path.read_text())
    capture = json.loads(Path(manifest['capture_path']).read_text())
    root = Path(manifest['capture_path']).parent
    rights = json.loads((root/capture['rights_path']).read_text())
    if manifest['contract_sha256'] != sha(contract_path):
        raise ValueError('Contract changed since dataset audit')
    if manifest['capture_sha256'] != sha(manifest['capture_path']):
        raise ValueError('Capture changed since dataset audit')
    if manifest['dataset_sha256'] != sha(manifest_path.parent/manifest['dataset_path']):
        raise ValueError('Dataset changed since audit')
    if canonical_sha256(rights) != manifest['rights_sha256']:
        raise ValueError('Reviewed rights digest differs')
    if sha(root/rights['evidence_path']) != rights['evidence_sha256']:
        raise ValueError('Reviewed source bytes changed')
    for page in capture['raw_files']+capture['identity_files']+capture['observation_files']+capture['subdivision_files']:
        if sha(root/page['path']) != page['sha256']:
            raise ValueError('Captured raw bytes changed')
    for key in ('strategy_concept_id','strategy_template_id','strategy_variant_id'):
        if getattr(contract,key) != previous['variant'][key]:
            raise ValueError('Frozen strategy identity differs')
    if contract.rule_ast != previous['variant']['rule_ast']:
        raise ValueError('Frozen source rule differs')
    review = copy.deepcopy(previous['reviewed_evidence'])
    for fact in [review['source']['artifact'],review['rule_evidence'],review['execution']['artifact']]:
        if sha(fact['uri']) != fact['sha256']:
            raise ValueError('Previously reviewed source/execution bytes changed')
    for item in review['rights']:
        if item['scope'] == 'MARKET_DATA':
            for key in ('research_use_allowed','research_use_scope','commercial_use_allowed',
                        'redistribution_allowed','derivative_allowed','attribution_required','attribution','rationale'):
                item[key]=rights[key]
            item.update(license_checked_at=rights['reviewed_at'],license_confidence=rights['confidence'],
                        license_source=rights['license_url'],
                        artifact=dict(uri=str((root/capture['rights_path']).resolve()),sha256=sha(root/capture['rights_path'])))
        elif sha(item['artifact']['uri']) != item['artifact']['sha256']:
            raise ValueError('Previously reviewed source permission bytes changed')
    review.update(reviewed_by='Codex trusted-market-v1 independent artifact review',
                  execution=contract.execution_contract,
                  derived_data_requirement=contract.data_requirements.model_dump(mode='json'),
                  warnings=['Source-derived long-only research adaptation; not exact original-strategy replication',
                            'Historical holdout previously exposed; not prospective evidence',
                            'Private internal market-data use only; no redistribution or live approval',
                            'Native optional quality fields absent; core profile uses independent finality and raw reconstruction'])
    review['data_requirement'].update(
        exchange=contract.provider,data_source=contract.source,symbols=contract.symbols,frequency=contract.frequency,
        start_date=contract.requested_start,end_date=contract.requested_end,real_market_data=manifest['real_market_data'],
        adjustment_method=contract.data_requirements.adjustment,timezone=contract.data_requirements.timezone,
        calendar=contract.data_requirements.calendar,
        required_fields=contract.data_requirements.required_fields,quality_status='PASS',
        data_availability_status='VERIFIED_AVAILABLE',dataset_hash=manifest['dataset_sha256'],
        dataset_version=manifest['dataset_version'],downloaded_at=capture['captured_at'],
        raw_data_hashes=[r['sha256'] for r in capture['raw_files']],
        evidence=dict(uri=str(manifest_path.resolve()),sha256=sha(manifest_path)))
    review['dataset_binding']=dict(
        contract_json=contract_text,contract_sha256=sha(contract_path),dataset_manifest_sha256=sha(manifest_path),
        rights_id=manifest['rights_id'],rights_sha256=manifest['rights_sha256'],rights_evidence=rights,
        coverage=manifest['coverage'],acceptance_status=manifest['acceptance_status'],
        missing_native_fields=manifest['missing_native_fields'],trust_assessment=manifest['trust_assessment'],
        trust_assessment_sha256=manifest['trust_assessment_sha256'])
    return EvidenceEnrichmentV4.model_validate(review).model_dump(mode='json')


def admit(db, contract_path, manifest_path, output):
    output=Path(output)
    if output.exists():raise ValueError('Use a new immutable admission output directory')
    contract=json.loads(Path(contract_path).read_text())
    repo=SQLiteIngestionRepository(db)
    previous=None
    for offset in range(0,repo.ingest_stats()['semantic_records'],1000):
        previous=next((r for r in repo.variants(1000,offset) if r['variant']['strategy_variant_id']==contract['strategy_variant_id']),None)
        if previous:break
    if not previous:raise ValueError('Existing reviewed strategy variant required')
    review=build_review(previous,contract_path,manifest_path)
    gate=evaluate(previous,review)
    if not gate['eligible']:raise ValueError('Gate rejected reviewed dataset: '+str(gate['blocking_reasons']))
    receipt=repo.review_record(review)
    # Read the persisted model through the normal projection/gate path.
    current=next(r for r in repo.variants(1000,offset) if r['variant']['strategy_variant_id']==contract['strategy_variant_id'])
    if not current['candidate_gate']['eligible']:raise ValueError('Persisted review not admitted')
    output.mkdir(parents=True,exist_ok=False)
    for name,value in [('candidate',current),('review',review),('transition',dict(
            before=previous['candidate_gate'],after=current['candidate_gate'],receipt=receipt,
            assessed_at=datetime.now(timezone.utc).isoformat(),promotion_allowed=False))]:
        (output/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return dict(receipt=receipt,gate=current['candidate_gate']['status'],candidate=str(output/'candidate.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for arg in ('db','contract','manifest','output'):p.add_argument('--'+arg,required=True,type=Path)
    a=p.parse_args();print(json.dumps(admit(a.db,a.contract,a.manifest,a.output)))
