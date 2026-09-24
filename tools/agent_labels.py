#!/usr/bin/env python3
"""Đọc label schema (ontology) thật của một project CVAT và in ra JSON.

    python tools/agent_labels.py --target local --project 5
    python tools/agent_labels.py --target local --project 5 --skeleton person

Mục đích: lấy mẫu `svg` hợp lệ của CVAT cho label skeleton. Guideline bắt buộc
schema skeleton phải có node/cạnh khớp tên sublabel, và cách duy nhất để biết
CVAT chấp nhận định dạng nào là đọc một schema đang chạy được.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover
            pass

from browser_agent.config import resolve_cvat  # noqa: E402
from browser_agent.cvat_rest import CvatClient, CvatError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default=None)
    parser.add_argument("--project", type=int, required=True)
    parser.add_argument("--skeleton", default=None, help="chỉ in label skeleton có tên này")
    parser.add_argument("--full", action="store_true", help="in toàn bộ, không cắt")
    args = parser.parse_args()

    client = CvatClient(resolve_cvat(args.target), timeout=30)
    try:
        project = client.request("GET", f"/projects/{args.project}")
    except CvatError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 3

    print(f"# Project {args.project}: {project.get('name')!r}")
    labels = project.get("labels") or []
    print(f"# {len(labels)} label")

    for label in labels:
        if args.skeleton and str(label.get("name", "")).lower() != args.skeleton.lower():
            continue
        payload = {
            "id": label.get("id"),
            "name": label.get("name"),
            "type": label.get("type"),
            "color": label.get("color"),
            "attributes": label.get("attributes"),
            "svg": label.get("svg"),
            "sublabels": [
                {
                    "id": sub.get("id"),
                    "name": sub.get("name"),
                    "type": sub.get("type"),
                    "attributes": sub.get("attributes"),
                }
                for sub in (label.get("sublabels") or [])
            ],
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        print(text if args.full else text[:2500])
        if not args.full and len(text) > 2500:
            print(f"... (cắt {len(text) - 2500} ký tự, dùng --full để xem hết)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
