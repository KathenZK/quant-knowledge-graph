#!/usr/bin/env python3
"""
Build normalized overlay v1 from off-repo audit work (2026-09-30).
Hash-pins each overlay entry to the source record's row_sha256 + rule_sha256.
Refreshes Lab coverage from repo's lab-display-sources.json.

Usage:
    python build_overlay.py <input_dir>
    
    input_dir: Directory containing 09-30 CSV inputs (strategies-normalized-v0_bb8a.csv, etc.)
"""
import csv
import json
import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime, timezone

from source_loader import load_source_records, WITHHELD_IDS

# Resolve paths relative to repo root
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent  # overlays/normalized-v1-20261008 -> overlays -> metadata -> repo_root
OVERLAY_DIR = SCRIPT_DIR
CORPUS_DIR = REPO_ROOT / "metadata/corpus-checkpoints/grokbot-6973-20261003"
LAB_DISPLAY = REPO_ROOT / "metadata/lab-display-sources.json"
CLASSIFICATIONS = REPO_ROOT / "metadata/classifications/20261004-v1/index.json"

def load_classifications() -> Dict[str, str]:
    """Load type classifications from main (authoritative)."""
    with open(CLASSIFICATIONS) as f:
        idx = json.load(f)
    
    types = {}
    
    # Read overrides which has the final classifications
    overrides_path = CLASSIFICATIONS.parent / "overrides.json"
    if overrides_path.exists():
        with open(overrides_path) as f:
            overrides = json.load(f)
            for record in overrides:
                types[record["record_id"]] = record.get("kind") or record.get("entity_type")
    
    # Also read decisions.jsonl
    decisions_path = CLASSIFICATIONS.parent / "decisions.jsonl"
    if decisions_path.exists():
        with open(decisions_path) as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    mid = record["record_id"]
                    if mid not in types:
                        types[mid] = record.get("kind") or record.get("entity_type")
    
    return types

def load_lab_coverage() -> Dict[str, Dict[str, Any]]:
    """Load Lab run registry for coverage refresh."""
    if not LAB_DISPLAY.exists():
        return {}
    
    with open(LAB_DISPLAY) as f:
        data = json.load(f)
    
    coverage = {}
    for record in data.get("records", []):
        mid = record["id"]
        coverage[mid] = {
            "lab_commit": record.get("lab_commit"),
            "run_id": record.get("run_id"),
            "variant_id": record.get("variant_id"),
            "fidelity_class": record.get("fidelity_class"),
            "group": record.get("group")
        }
    
    return coverage

def main():
    if len(sys.argv) < 2:
        print("Usage: python build_overlay.py <input_dir>")
        print("  input_dir: Directory containing 09-30 CSV inputs")
        return 1
    
    input_dir = Path(sys.argv[1]).resolve()
    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}")
        return 1
    
    print("Loading source records...")
    source_records = load_source_records(CORPUS_DIR)
    print(f"  Loaded {len(source_records)} source records")
    
    print("Loading type classifications from main...")
    classifications = load_classifications()
    print(f"  Loaded {len(classifications)} classifications")
    
    print("Loading Lab coverage...")
    lab_coverage = load_lab_coverage()
    print(f"  Loaded {len(lab_coverage)} Lab runs")
    
    print(f"\nReading normalized strategies CSV...")
    strategies = []
    with open(input_dir / "strategies-normalized-v0_bb8a.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            strategies.append(row)
    print(f"  Read {len(strategies)} rows")
    
    print(f"\nReading families CSV...")
    families = []
    with open(input_dir / "families-v0_c288.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            families.append(row)
    print(f"  Read {len(families)} families")
    
    print(f"\nReading variants CSV...")
    variants = []
    with open(input_dir / "variants-v0_410e.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            variants.append(row)
    print(f"  Read {len(variants)} variants")
    
    print(f"\nReading known issues...")
    with open(input_dir / "known-issues-verification-v1_2a77.json") as f:
        known_issues = json.load(f)
    
    print(f"\nReading coverage matrix...")
    coverage_matrix = {}
    with open(input_dir / "coverage-matrix-v1_7028.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            coverage_matrix[row["id"]] = row
    
    # Build overlay entries
    print("\nBuilding overlay entries...")
    overlay_entries = []
    discrepancies = []
    missing_hashes = []
    type_conflicts = []
    
    for row in strategies:
        mid = row["id"]
        
        # Skip withheld IDs (documented, not an error)
        if mid in WITHHELD_IDS:
            continue
        
        # Get source record hashes
        if mid not in source_records:
            missing_hashes.append(mid)
            continue
        
        hashes = source_records[mid]
        
        # Check type classification conflict
        main_type = classifications.get(mid)
        
        # Build overlay entry
        entry = {
            "id": mid,
            "pinned_to": {
                "row_sha256": hashes["row_sha256"],
                "rule_sha256": hashes["rule_sha256"],
                "csv_row_ordinal": hashes["csv_row_ordinal"]
            },
            "family_id": row.get("family_id") or None,
            "provisional_family_key": row.get("provisional_family_key") or None,
            "implementation_id": row.get("implementation_id") or None,
            "variant_id": row.get("variant_id") or None,
            "parent_id": row.get("parent_id") or None,
            "origin_type": row.get("origin_type"),
            "source_rule": row.get("source_rule") or None,
            "implementation_rule": row.get("implementation_rule") or None,
            "attribution": {},
            "dates": {
                "indicator_origin_year": row.get("indicator_origin_year") or None,
                "source_published_at": row.get("source_published_at") or None,
                "source_updated_at": row.get("source_updated_at") or None,
                "implementation_first_documented_at": row.get("implementation_first_documented_at") or None,
                "retrieved_at": row.get("retrieved_at") or None,
                "date_precision": row.get("date_precision") or "unknown"
            },
            "statuses": {
                "source_verified": row.get("source_verified") or "unverified",
                "spec_status": row.get("spec_status") or "unknown",
                "data_status": row.get("data_status") or "unknown",
                "implementation_status": row.get("implementation_status") or "unknown",
                "access_status": row.get("access_status") or "unknown"
            },
            "legacy_result_label": row.get("result_status") or None,
            "disposition": row.get("disposition") or "unknown",
            "confidence": row.get("confidence") or "heuristic"
        }
        
        # Add attribution flags
        for attr in ["universe", "thresholds", "lookbacks", "frequency", "entry", 
                     "exit", "sizing", "cash_asset", "stop", "displacement", "fill_timing"]:
            col = f"attr_{attr}"
            if col in row and row[col]:
                entry["attribution"][attr] = row[col]
        
        # Add Lab coverage if available
        if mid in lab_coverage:
            entry["lab_coverage"] = lab_coverage[mid]
            # Update coverage status from 09-30 matrix
            if mid in coverage_matrix:
                old_status = coverage_matrix[mid].get("backtest_coverage_status")
                entry["coverage_note"] = f"2026-09-30: {old_status}; refreshed from Lab registry 2026-10-08"
        elif mid in coverage_matrix:
            # Use 09-30 status
            entry["backtest_coverage_status_20260930"] = coverage_matrix[mid].get("backtest_coverage_status")
        
        # Check for known issues
        for ki in known_issues.get("records", []):
            if ki["id"] == mid:
                if "known_issues" not in entry:
                    entry["known_issues"] = []
                entry["known_issues"].append({
                    "family": ki.get("family"),
                    "disposition": ki.get("disposition"),
                    "verified_at": ki.get("verified_at")
                })
        
        overlay_entries.append(entry)
    
    print(f"  Built {len(overlay_entries)} overlay entries")
    print(f"  Missing hashes: {len(missing_hashes)}")
    if missing_hashes:
        print(f"    First 10: {missing_hashes[:10]}")
    
    # Save overlay entries as JSONL
    overlay_file = OVERLAY_DIR / "normalized-records.jsonl"
    with open(overlay_file, "w") as f:
        for entry in overlay_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"\nWrote {overlay_file}")
    
    # Save families
    families_file = OVERLAY_DIR / "families.json"
    with open(families_file, "w") as f:
        json.dump([dict(fam) for fam in families], f, indent=2, ensure_ascii=False)
    print(f"Wrote {families_file}")
    
    # Save variants
    variants_file = OVERLAY_DIR / "variants.json"
    with open(variants_file, "w") as f:
        json.dump([dict(var) for var in variants], f, indent=2, ensure_ascii=False)
    print(f"Wrote {variants_file}")
    
    # Save discrepancies report
    discrepancies_file = OVERLAY_DIR / "discrepancies.json"
    with open(discrepancies_file, "w") as f:
        json.dump({
            "withheld_ids": sorted(WITHHELD_IDS),
            "missing_source_record_hashes": missing_hashes,
            "type_classification_conflicts": type_conflicts,
            "notes": [
                "withheld_ids: M2535/M2709 intentionally excluded from public corpus per existing policy",
                "missing_source_record_hashes: M-IDs in normalized CSV but not found in corpus (after checking batches + subsets)",
                "Type classifications intentionally excluded from overlay per design"
            ]
        }, f, indent=2, ensure_ascii=False)
    print(f"Wrote {discrepancies_file}")
    
    # Build summary
    summary = {
        "version": "normalized-v1-20261008",
        "generated_at": "2026-10-08T03:40:00Z",
        "source_data": {
            "normalized_csv": "strategies-normalized-v0_bb8a.csv",
            "csv_md5": "f3c60e61bedfd0434c339cb4c16a7e4a",
            "rows_processed": len(strategies)
        },
        "counts": {
            "overlay_entries": len(overlay_entries),
            "families": len(families),
            "variants": len(variants),
            "lab_coverage_refreshed": len([e for e in overlay_entries if "lab_coverage" in e]),
            "known_issues_annotated": len([e for e in overlay_entries if "known_issues" in e])
        },
        "lab_refresh": {
            "lab_registry_path": str(LAB_DISPLAY.relative_to(REPO_ROOT)),
            "lab_runs_found": len(lab_coverage),
            "newly_executed_since_20260930": []
        },
        "discrepancies": {
            "missing_hashes": len(missing_hashes)
        }
    }
    
    # Identify newly executed IDs
    newly_executed = []
    lab_refresh_details = []
    for mid, lab_info in lab_coverage.items():
        old_status = None
        if mid in coverage_matrix:
            old_coverage_class = coverage_matrix[mid].get("backtest_coverage_class") or coverage_matrix[mid].get("coverage_class")
            old_result_status = coverage_matrix[mid].get("result_status")
            old_legacy_bucket = coverage_matrix[mid].get("legacy_bucket") or coverage_matrix[mid].get("validation_bucket")
            
            # Check if it was not_executed in 09-30 matrix
            if old_coverage_class == "not_executed" or old_result_status == "not_run":
                newly_executed.append(mid)
                lab_refresh_details.append({
                    "id": mid,
                    "old_coverage_class": old_coverage_class,
                    "old_result_status": old_result_status,
                    "old_legacy_bucket": old_legacy_bucket,
                    "new_fidelity_class": lab_info["fidelity_class"],
                    "lab_commit": lab_info["lab_commit"],
                    "run_id": lab_info["run_id"]
                })
    
    summary["lab_refresh"]["newly_executed_since_20260930"] = sorted(newly_executed)
    summary["lab_refresh"]["newly_executed_count"] = len(newly_executed)
    summary["lab_refresh"]["lab_refresh_details"] = lab_refresh_details
    
    summary_file = OVERLAY_DIR / "summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Wrote {summary_file}")
    
    print("\n✓ Overlay build complete")
    return 0

if __name__ == "__main__":
    exit(main())
