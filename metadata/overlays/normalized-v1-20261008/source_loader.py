#!/usr/bin/env python3
"""
Shared source record loader for overlay builder and validator.
Scans both batches/ and subsets/ directories.
"""
import json
from pathlib import Path
from typing import Dict, Any

# Known withheld IDs (intentionally excluded from public corpus)
WITHHELD_IDS = {"M2535", "M2709"}


def load_source_records(corpus_dir: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load all source records to get their hash fingerprints.
    
    Returns:
        Dict mapping M-ID to {row_sha256, rule_sha256, csv_row_ordinal}
    """
    records = {}
    
    # Scan all batches
    for batch_dir in sorted(corpus_dir.glob("batches/batch-*")):
        source_dir = batch_dir / "metadata/source-records"
        if not source_dir.exists():
            continue
            
        for record_file in source_dir.glob("M*.json"):
            with open(record_file) as f:
                data = json.load(f)
                mid = data["record_id"]
                records[mid] = {
                    "row_sha256": data["provenance"]["row_sha256"],
                    "rule_sha256": data["provenance"]["rule_sha256"],
                    "csv_row_ordinal": data["provenance"]["csv_row_ordinal"]
                }
    
    # Scan subsets (e.g., batch-0026-public-v1, batch-0028-public-v1)
    subsets_dir = corpus_dir / "subsets"
    if subsets_dir.exists():
        for subset_dir in sorted(subsets_dir.glob("batch-*")):
            source_dir = subset_dir / "metadata/source-records"
            if not source_dir.exists():
                continue
                
            for record_file in source_dir.glob("M*.json"):
                with open(record_file) as f:
                    data = json.load(f)
                    mid = data["record_id"]
                    if mid not in records:  # Don't overwrite if already found
                        records[mid] = {
                            "row_sha256": data["provenance"]["row_sha256"],
                            "rule_sha256": data["provenance"]["rule_sha256"],
                            "csv_row_ordinal": data["provenance"]["csv_row_ordinal"]
                        }
    
    return records
