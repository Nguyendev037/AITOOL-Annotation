#!/usr/bin/env python3
"""Generate Nuclio function.yaml label spec from guideline markdown.

Usage:
    python tools/gen_labels.py
    python tools/gen_labels.py --guideline guideline/semantic_segmentation.md --task semantic_segmentation
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "model-service"))
from guideline_agent import extract_labels_from_guideline, generate_labels_with_llm, generate_nuclio_spec


def main():
    parser = argparse.ArgumentParser(description="Generate Nuclio label spec from guideline")
    parser.add_argument("--guideline", default="guideline/semantic_segmentation.md")
    parser.add_argument("--task", default="semantic_segmentation", choices=["semantic_segmentation", "instance_segmentation", "object_detection", "keypoint"])
    parser.add_argument("--use-llm", action="store_true", help="Use DeepSeek LLM for label extraction")
    parser.add_argument("--output", default=None, help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    guideline_path = root / args.guideline
    guideline_text = guideline_path.read_text(encoding="utf-8")

    if args.use_llm:
        labels = generate_labels_with_llm(guideline_text, task_type=args.task)
    else:
        names = extract_labels_from_guideline(guideline_text)
        shape_map = {"semantic_segmentation": "mask", "instance_segmentation": "polygon", "object_detection": "rectangle", "keypoint": "skeleton"}
        labels = [{"name": n, "type": shape_map.get(args.task, "rectangle")} for n in names]

    spec = generate_nuclio_spec(labels)
    if args.output:
        out = root / args.output
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(spec, encoding="utf-8")
        print(f"Written {len(labels)} labels to {out}")
    else:
        print(spec)


if __name__ == "__main__":
    main()
