#!/usr/bin/env python3
"""Cross-platform Nuclio smoke invocation using nuctl and a local image."""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("function", help="Nuclio function name")
    ap.add_argument("image")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--nuctl", default="nuctl")
    args = ap.parse_args()

    image = Path(args.image)
    payload = {
        "image": base64.b64encode(image.read_bytes()).decode("ascii"),
        "threshold": args.threshold,
    }
    p = subprocess.run(
        [args.nuctl, "invoke", args.function, "--platform", "local", "-c", "application/json"],
        input=json.dumps(payload), text=True, capture_output=True,
    )
    print(p.stdout)
    if p.stderr:
        print(p.stderr)
    raise SystemExit(p.returncode)


if __name__ == "__main__":
    main()
