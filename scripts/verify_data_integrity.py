#!/usr/bin/env python3
"""Check the GUIDE CSVs on this machine against the committed integrity manifest.

M1.2 Part D (issue #30). The datasets are 3.4 GB combined and gitignored, so
every reader supplies their own copy. Nothing until now checked that the copy
they supplied is the same release the results were computed from -- a truncated
download or a different GUIDE version would silently produce different numbers
with no indication that anything was wrong.

Exit codes: 0 = every file matches, 1 = something differs or is missing.

usage (from repo root):
    python scripts/verify_data_integrity.py
    python scripts/verify_data_integrity.py --write    # regenerate the manifest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "datasets" / "INTEGRITY_MANIFEST.json"
TRACKED = ["datasets/GUIDE_train.csv", "datasets/GUIDE_Test.csv"]

CHUNK = 8 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    size = path.stat().st_size
    read = 0
    with open(path, "rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
            read += len(chunk)
            pct = 100 * read / size if size else 100
            print(f"\r  hashing {path.name}: {pct:5.1f}%", end="", flush=True)
    print()
    return digest.hexdigest()


def describe(relative: str) -> dict:
    path = REPO_ROOT / relative
    stat = path.stat()
    return {
        "path": relative,
        "sha256": sha256(path),
        "file_size_bytes": stat.st_size,
        "last_modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def write_manifest() -> int:
    missing = [r for r in TRACKED if not (REPO_ROOT / r).exists()]
    if missing:
        print(f"cannot write a manifest: missing {', '.join(missing)}", file=sys.stderr)
        return 1
    manifest = {
        "dataset": "Microsoft GUIDE (Ronen et al., 2024)",
        "licence": "CDLA-Permissive-2.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": (
            "SHA-256 of the exact GUIDE release every committed result in "
            "experiments/results/ was computed from. Verify with "
            "scripts/verify_data_integrity.py before trusting a re-run."
        ),
        "files": [describe(r) for r in TRACKED],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {MANIFEST_PATH}")
    return 0


def verify() -> int:
    if not MANIFEST_PATH.exists():
        print(f"no manifest at {MANIFEST_PATH}; run with --write to create one.", file=sys.stderr)
        return 1

    manifest = json.loads(MANIFEST_PATH.read_text())
    failures: list[str] = []

    print(f"verifying {len(manifest['files'])} file(s) against {MANIFEST_PATH.name}\n")
    for entry in manifest["files"]:
        relative = entry["path"]
        path = REPO_ROOT / relative
        if not path.exists():
            failures.append(f"{relative}: MISSING (see datasets/README.md for the download)")
            print(f"  {relative}: MISSING")
            continue

        actual_size = path.stat().st_size
        if actual_size != entry["file_size_bytes"]:
            delta = actual_size - entry["file_size_bytes"]
            failures.append(
                f"{relative}: SIZE MISMATCH -- expected {entry['file_size_bytes']:,} bytes, "
                f"found {actual_size:,} ({delta:+,}). A truncated or partial download is the "
                f"usual cause."
            )
            print(f"  {relative}: SIZE MISMATCH ({delta:+,} bytes) -- not hashing")
            continue

        actual = sha256(path)
        if actual != entry["sha256"]:
            failures.append(
                f"{relative}: SHA-256 MISMATCH\n"
                f"      expected {entry['sha256']}\n"
                f"      found    {actual}\n"
                f"      Same size, different contents: this is a different GUIDE release. "
                f"Results computed from it will not match the committed ones."
            )
            print(f"  {relative}: SHA-256 MISMATCH")
        else:
            print(f"  {relative}: OK ({actual_size:,} bytes)")

    print()
    if failures:
        print("=" * 72)
        print(" DATA INTEGRITY CHECK FAILED")
        print("=" * 72)
        for f in failures:
            print(f"  - {f}")
        return 1

    print("=" * 72)
    print(" DATA INTEGRITY CHECK PASSED -- datasets match the committed manifest")
    print("=" * 72)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate the manifest from local files")
    args = parser.parse_args()
    return write_manifest() if args.write else verify()


if __name__ == "__main__":
    raise SystemExit(main())
