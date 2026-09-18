#!/usr/bin/env python3
"""Static validator for a CVAT model integration scaffold/implementation."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LABEL_TYPES = {"any", "cuboid", "ellipse", "mask", "points", "polygon", "polyline", "rectangle", "skeleton", "interval", "tag"}
COMMON_DIRECT_TYPES = {"rectangle", "polygon", "mask", "skeleton", "points"}


def extract_annotations_spec(text: str):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^\s{4}spec:\s*\|\s*$", line):
            block = []
            base_indent = 6
            for nxt in lines[i + 1:]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) < base_indent:
                    break
                block.append(nxt[base_indent:] if len(nxt) >= base_indent else "")
            raw = "\n".join(block).strip()
            return json.loads(raw)
    raise ValueError("metadata.annotations.spec block not found or not parseable")


def validate_skeleton(label, errors, warnings):
    subs = label.get("sublabels")
    svg = label.get("svg")
    if not isinstance(subs, list) or not subs:
        errors.append(f"skeleton label {label.get('name')!r} has no sublabels")
        return
    names = [str(x.get("name")) for x in subs]
    if len(set(names)) != len(names):
        errors.append(f"skeleton label {label.get('name')!r} has duplicate sublabel names")
    if not svg:
        warnings.append(f"skeleton label {label.get('name')!r} has no SVG; confirm this is accepted by the target CVAT revision")
        return
    svg_names = re.findall(r'data-label-name=["\']([^"\']+)["\']', svg)
    missing = sorted(set(names) - set(svg_names))
    if missing:
        errors.append(f"skeleton SVG for {label.get('name')!r} is missing data-label-name entries: {missing}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="Integration directory containing model_manifest.json")
    args = ap.parse_args()
    root = Path(args.path).resolve()
    errors, warnings = [], []

    manifest_path = root / "model_manifest.json"
    if not manifest_path.exists():
        errors.append("model_manifest.json missing")
        manifest = {}
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"model_manifest.json invalid: {exc}")
            manifest = {}

    mode = manifest.get("integration_mode")
    labels = manifest.get("labels", [])
    if mode not in {"direct", "sidecar", "batch"}:
        errors.append(f"unknown integration_mode: {mode!r}")
    if not labels:
        errors.append("manifest contains no labels")
    for label in labels:
        typ = label.get("type")
        if typ not in LABEL_TYPES:
            errors.append(f"label {label.get('name')!r} has invalid type {typ!r}")
        if typ == "skeleton":
            validate_skeleton(label, errors, warnings)
        if mode in {"direct", "sidecar"} and manifest.get("function_kind") == "detector" and typ not in COMMON_DIRECT_TYPES:
            warnings.append(
                f"label type {typ!r} may not be exposed by the target CVAT Nuclio/UI path; verify against the local checkout and use SDK batch fallback rather than approximating geometry."
            )

    if mode in {"direct", "sidecar"}:
        for name in ("function.yaml", "main.py", "model_handler.py"):
            if not (root / name).exists():
                errors.append(f"{name} missing")
        fy = root / "function.yaml"
        if fy.exists():
            txt = fy.read_text(encoding="utf-8", errors="replace")
            for needle in ("metadata:", "annotations:", "type:", "handler: main:handler", "triggers:"):
                if needle not in txt:
                    errors.append(f"function.yaml missing {needle!r}")
            if manifest.get("function_kind") == "detector":
                try:
                    spec = extract_annotations_spec(txt)
                    spec_names = [x.get("name") for x in spec if isinstance(x, dict)]
                    manifest_names = [x.get("name") for x in labels if isinstance(x, dict)]
                    if spec_names != manifest_names:
                        errors.append("function.yaml label names/order do not match model_manifest.json")
                except Exception as exc:
                    errors.append(f"function.yaml annotations spec invalid: {exc}")
        mh = root / "model_handler.py"
        if mh.exists() and "NotImplementedError" in mh.read_text(encoding="utf-8", errors="replace"):
            errors.append("model_handler.py still contains NotImplementedError; implementation is incomplete")
    elif mode == "batch":
        if not (root / "batch_auto_annotate.py").exists():
            errors.append("batch_auto_annotate.py missing")

    if not manifest.get("model_revision") and manifest.get("model_source"):
        warnings.append("model source is not pinned to an exact revision/checksum; reproducibility is weak")
    if manifest.get("status") != "tested":
        warnings.append(f"manifest status is {manifest.get('status')!r}; final delivery should set status='tested' only after end-to-end verification")

    print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, indent=2))
    sys.exit(0 if not errors else 2)


if __name__ == "__main__":
    main()
