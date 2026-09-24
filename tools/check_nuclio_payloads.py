#!/usr/bin/env python3
"""Verify a generated nuclio payload before it is POSTed to the dashboard."""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payloads", nargs="*", default=None)
    args = parser.parse_args()

    build = ROOT / "nuclio" / "build"
    manifest = json.loads((build / "manifest.json").read_text(encoding="utf-8"))
    names = args.payloads or manifest["functions"]

    failures = 0
    for name in names:
        path = build / f"{name}.json"
        if not path.is_file():
            print(f"{name}: MISSING {path}")
            failures += 1
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        spec = payload.get("spec", {})
        env = {entry["name"]: entry.get("value") for entry in spec.get("env", [])}
        source_code = spec.get("build", {}).get("functionSourceCode")

        problems: list[str] = []
        if payload.get("metadata", {}).get("name") != name:
            problems.append("metadata.name mismatch")
        if not source_code:
            problems.append("no functionSourceCode")
        task = env.get("TASK")
        if not task:
            problems.append("no TASK env")
        taxonomy_raw = env.get("TAXONOMY_JSON")
        declared: list[str] = []
        if not taxonomy_raw:
            problems.append("no TAXONOMY_JSON")
        else:
            taxonomy = json.loads(taxonomy_raw)
            declared = taxonomy.get("declared", [])
            if not declared:
                problems.append("TAXONOMY_JSON declares no labels")

        spec_block = payload.get("metadata", {}).get("annotations", {}).get("spec", "")
        spec_labels = [
            json.loads(line.strip().rstrip(","))["name"]
            for line in spec_block.splitlines()
            if line.strip().startswith("{")
        ]
        if spec_labels != declared:
            problems.append(f"spec labels {spec_labels} != declared {declared}")

        status = "OK " if not problems else "BAD"
        print(f"{status} {name:16s} task={task!s:9s} labels={len(declared):2d} "
              f"src={len(source_code or '')} b64 chars")
        print(f"      labels: {', '.join(declared) if declared else '-'}")
        for problem in problems:
            print(f"      !! {problem}")
        failures += len(problems)

    print()
    print("all payloads consistent" if not failures else f"{failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
