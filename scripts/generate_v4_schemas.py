"""Generate Graph contracts; optional explicit Lab destination for sync."""
import argparse
import json
from pathlib import Path
from quantgraph.models import market,evidence_v4

CONTRACTS=[('MarketDatasetTrustAssessment','market_dataset_trust_v1',market),('ResearchContract','research_contract_v4',market),('ReviewedRightsEvidence','reviewed_rights_v4',market),
 ('MarketCoverage','market_coverage_v4',market),('EvidenceEnrichmentV4','evidence_enrichment_v4',evidence_v4),
 ('MarketResearchEvidenceV4','market_research_evidence_v4',evidence_v4),
 ('ResearchCandidateAssessmentV4','research_candidate_assessment_v4',evidence_v4)]


def generate(root,lab=None):
    for name,file,module in CONTRACTS:
        data=json.dumps(getattr(module,name).model_json_schema(),sort_keys=True,indent=2)+'\n'
        (root/'models/schemas'/(name+'.schema.json')).write_text(data)
        if lab:(lab/(file+'.schema.json')).write_text(data)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--lab-schema-dir',type=Path);a=p.parse_args()
    generate(Path(__file__).resolve().parents[1],a.lab_schema_dir)
