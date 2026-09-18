#!/usr/bin/env python3
"""Invoke a deployed nuclio function exactly the way CVAT does.

CVAT sends one frame per request as a JSON body ``{"image": "<base64>"}`` and
expects a JSON list of annotations back. This script reproduces that call so a
function can be verified without opening the CVAT UI.

The nuclio dashboard is not published on the host, so both the dashboard call
and the function invocation run inside throwaway ``curlimages/curl`` containers
attached to the CVAT docker network.

Usage
-----
    python tools/smoke_nuclio.py --function smart-bbox --image test/detect/G01_B026.jpg
    python tools/smoke_nuclio.py --function smart-semantic --image test/detect/G01_B026.jpg --dump
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "nuclio" / "build"


def _curl(args: list[str], network: str, timeout: int = 600, extra_mounts: list[str] | None = None) -> str:
    cmd = ["docker", "run", "--rm", "--network", network]
    for mount in extra_mounts or []:
        cmd += ["-v", mount]
    cmd += ["curlimages/curl", "-s", "-S", "-m", str(timeout)] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise SystemExit(f"curl container failed:\n{proc.stderr.strip()}")
    return proc.stdout


def _function_info(name: str, network: str, dashboard: str) -> dict:
    raw = _curl([f"{dashboard}/api/functions/{name}"], network)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(f"could not read function {name!r} from the dashboard:\n{raw[:600]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--function", required=True, help="nuclio function name, e.g. smart-bbox")
    parser.add_argument("--image", required=True, help="path to a .jpg/.png frame")
    parser.add_argument("--network", default="cvat_cvat")
    parser.add_argument("--dashboard", default="http://nuclio:8070")
    parser.add_argument("--threshold", type=float, help="value CVAT would send as `threshold`")
    parser.add_argument("--dump", action="store_true", help="print the full annotation list")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.is_file():
        image_path = REPO_ROOT / args.image
    if not image_path.is_file():
        raise SystemExit(f"image not found: {args.image}")

    info = _function_info(args.function, args.network, args.dashboard)
    state = info.get("status", {}).get("state")
    urls = info.get("status", {}).get("internalInvocationUrls") or []
    if state != "ready":
        raise SystemExit(f"function {args.function!r} is {state!r}, not ready. Check tools/nuclio_status.ps1")
    if not urls:
        raise SystemExit(f"function {args.function!r} has no internal invocation URL yet")

    body = {"image": base64.b64encode(image_path.read_bytes()).decode("ascii")}
    if args.threshold is not None:
        body["threshold"] = args.threshold

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    request_path = BUILD_DIR / f"request-{args.function}.json"
    request_path.write_text(json.dumps(body), encoding="utf-8")

    endpoint = f"http://{urls[0]}/"
    print(f"POST {endpoint}  ({image_path.name}, {len(body['image']) // 1024} KiB base64)")

    raw = _curl([
        "-X", "POST", endpoint,
        "-H", "Content-Type: application/json",
        "--data-binary", f"@/repo/nuclio/build/{request_path.name}",
    ], args.network, extra_mounts=[f"{REPO_ROOT}:/repo:ro"])

    try:
        annotations = json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(f"function returned non-JSON:\n{raw[:1500]}")

    if isinstance(annotations, dict) and annotations.get("error"):
        raise SystemExit(f"function returned an error: {annotations['error']}")

    counts = Counter(item.get("label", "?") for item in annotations)
    types = Counter(item.get("type", "?") for item in annotations)
    print(f"\nannotations: {len(annotations)}")
    print(f"  types : {dict(types)}")
    print(f"  labels: {dict(counts)}")

    if args.dump:
        print()
        for item in annotations[:15]:
            points = item.get("points", [])
            preview = ", ".join(f"{v:.1f}" for v in points[:8])
            print(f"  {item.get('label'):<18} {item.get('type'):<10} conf={item.get('confidence')} [{preview}{' ...' if len(points) > 8 else ''}]")
        if len(annotations) > 15:
            print(f"  ... {len(annotations) - 15} more")

    return 0 if annotations else 1


if __name__ == "__main__":
    sys.exit(main())
