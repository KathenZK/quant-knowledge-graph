"""
Test suite for normalized overlay v1.
"""
import json
import pytest
from pathlib import Path

# Resolve paths relative to repo root
TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parent
OVERLAY_DIR = REPO_ROOT / "metadata/overlays/normalized-v1-20261008"

def test_overlay_files_exist():
    """Check all expected files exist."""
    expected_files = [
        "normalized-records.jsonl",
        "families.json",
        "variants.json",
        "discrepancies.json",
        "summary.json",
        "schema.md",
        "README.md",
        "manifest.json",
        "build_overlay.py",
        "validate_overlay.py",
        "generate_manifest.py"
    ]
    
    for filename in expected_files:
        filepath = OVERLAY_DIR / filename
        assert filepath.exists(), f"Missing file: {filename}"

def test_manifest_integrity():
    """Check manifest matches actual files."""
    with open(OVERLAY_DIR / "manifest.json") as f:
        manifest = json.load(f)
    
    for filename, info in manifest["files"].items():
        filepath = OVERLAY_DIR / filename
        assert filepath.exists(), f"Manifest references missing file: {filename}"
        assert filepath.stat().st_size == info["bytes"], f"Size mismatch for {filename}"

def test_overlay_records_structure():
    """Check overlay records have required fields."""
    records = []
    with open(OVERLAY_DIR / "normalized-records.jsonl") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    
    assert len(records) > 0, "No overlay records found"
    
    required_fields = ["id", "pinned_to", "origin_type", "statuses", "dates"]
    
    for rec in records[:10]:  # Test first 10
        for field in required_fields:
            assert field in rec, f"Missing field {field} in record {rec.get('id')}"
        
        assert "row_sha256" in rec["pinned_to"]
        assert "rule_sha256" in rec["pinned_to"]
        assert "csv_row_ordinal" in rec["pinned_to"]

def test_families_structure():
    """Check families file structure."""
    with open(OVERLAY_DIR / "families.json") as f:
        families = json.load(f)
    
    assert isinstance(families, list)
    assert len(families) > 0
    
    # Check first family has expected fields
    if families:
        fam = families[0]
        assert "family_id" in fam
        assert "provisional_family_key" in fam

def test_variants_structure():
    """Check variants file structure."""
    with open(OVERLAY_DIR / "variants.json") as f:
        variants = json.load(f)
    
    assert isinstance(variants, list)
    assert len(variants) > 0
    
    # Check first variant has expected fields
    if variants:
        var = variants[0]
        assert "variant_id" in var
        assert "id" in var
        assert "parent_id" in var

def test_summary_counts():
    """Check summary counts are reasonable."""
    with open(OVERLAY_DIR / "summary.json") as f:
        summary = json.load(f)
    
    counts = summary["counts"]
    assert counts["overlay_entries"] > 6000
    assert counts["families"] > 6000
    assert counts["variants"] > 600
    assert counts["lab_coverage_refreshed"] > 0
    assert counts["known_issues_annotated"] == 15

def test_discrepancies():
    """Check discrepancies are documented."""
    with open(OVERLAY_DIR / "discrepancies.json") as f:
        disc = json.load(f)
    
    assert "withheld_ids" in disc
    assert "missing_source_record_hashes" in disc
    assert "notes" in disc
    # With subsets included, all 6971 records should be pinned (only M2535/M2709 withheld)
    assert len(disc["withheld_ids"]) == 2

def test_lab_coverage_refresh():
    """Check Lab coverage was refreshed."""
    with open(OVERLAY_DIR / "summary.json") as f:
        summary = json.load(f)
    
    lab_info = summary["lab_refresh"]
    assert "lab_runs_found" in lab_info
    assert lab_info["lab_runs_found"] == 27
    assert "newly_executed_since_20260930" in lab_info

def test_full_validator():
    """Run the complete validator to check source record pins."""
    import subprocess
    
    validator_path = OVERLAY_DIR / "validate_overlay.py"
    result = subprocess.run(
        ["python3", str(validator_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True
    )
    
    # Validator should exit 0 when all checks pass
    assert result.returncode == 0, f"Validator failed:\n{result.stdout}\n{result.stderr}"
    
    # Check for success messages
    assert "✓ All M-IDs exist in source records" in result.stdout
    assert "✓ All hash pins match source records" in result.stdout

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
