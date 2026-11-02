#!/usr/bin/env python3
"""
Generate manifest with SHA-256 hashes for all overlay files.
"""
import hashlib
import json
from pathlib import Path

def sha256_file(path: Path) -> str:
    """Calculate SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def main():
    overlay_dir = Path(__file__).parent
    
    files_to_hash = [
        "normalized-records.jsonl",
        "families.json",
        "variants.json",
        "discrepancies.json",
        "summary.json",
        "schema.md",
        "README.md",
        "build_overlay.py"
    ]
    
    manifest = {
        "version": "normalized-v1-20261008",
        "generated_at": "2026-10-08T03:40:00Z",
        "files": {}
    }
    
    for filename in files_to_hash:
        filepath = overlay_dir / filename
        if filepath.exists():
            manifest["files"][filename] = {
                "sha256": sha256_file(filepath),
                "bytes": filepath.stat().st_size
            }
    
    manifest_path = overlay_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Wrote {manifest_path}")
    print(f"  {len(manifest['files'])} files cataloged")

if __name__ == "__main__":
    main()
