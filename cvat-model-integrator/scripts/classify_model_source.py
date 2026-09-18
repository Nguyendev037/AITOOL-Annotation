#!/usr/bin/env python3
"""Classify a model source and emit a reproducibility manifest fragment.

No network calls are made. For local files, records SHA-256 and size.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(source: str):
    p = Path(source).expanduser()
    out = {"source": source, "source_type": "model_name", "revision": None, "sha256": None, "size_bytes": None}
    if p.exists():
        out["source_type"] = "local_directory" if p.is_dir() else "local_file"
        out["resolved_path"] = str(p.resolve())
        if p.is_file():
            out["sha256"] = sha256(p)
            out["size_bytes"] = p.stat().st_size
            out["extension"] = p.suffix.lower()
        return out

    parsed = urlparse(source)
    host = (parsed.netloc or "").lower()
    if host.endswith("github.com"):
        out["source_type"] = "github"
        parts = [x for x in parsed.path.split("/") if x]
        if len(parts) >= 2:
            out["repository"] = f"{parts[0]}/{parts[1].removesuffix('.git')}"
        m = re.search(r"/(?:tree|blob)/([^/]+)", parsed.path)
        if m:
            out["revision"] = m.group(1)
        return out
    if host.endswith("huggingface.co"):
        out["source_type"] = "huggingface"
        parts = [x for x in parsed.path.split("/") if x]
        if len(parts) >= 2:
            out["repository"] = f"{parts[0]}/{parts[1]}"
        m = re.search(r"/(?:tree|blob)/([^/]+)", parsed.path)
        if m:
            out["revision"] = m.group(1)
        return out
    if parsed.scheme in {"http", "https"}:
        out["source_type"] = "url"
        return out
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--revision", help="Pinned commit/tag/revision if known")
    args = ap.parse_args()
    out = classify(args.source)
    if args.revision:
        out["revision"] = args.revision
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
