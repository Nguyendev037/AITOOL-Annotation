#!/usr/bin/env python3
"""Cross-platform probe for a Git-cloned CVAT + Docker Compose environment.

Uses only Python standard library. It never mutates the repository.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd=None, timeout=12):
    try:
        p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
        return {"ok": p.returncode == 0, "code": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    except Exception as exc:
        return {"ok": False, "code": None, "stdout": "", "stderr": str(exc)}


def find_repo(start: Path) -> Path | None:
    p = start.resolve()
    for candidate in [p, *p.parents]:
        if (candidate / "docker-compose.yml").exists() and (candidate / "serverless").exists():
            return candidate
    return None


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def parse_nuclio_image(compose_text: str):
    m = re.search(r"image:\s*['\"]?([^\s'\"]*nuclio/dashboard:[^\s'\"]+)", compose_text, re.I)
    if not m:
        return {"image": None, "version": None, "image_arch": None}
    image = m.group(1)
    tag = image.rsplit(":", 1)[-1]
    vm = re.match(r"(?P<version>\d+\.\d+(?:\.\d+)?)(?:-(?P<arch>[A-Za-z0-9_\-]+))?", tag)
    return {
        "image": image,
        "version": vm.group("version") if vm else None,
        "image_arch": vm.group("arch") if vm else None,
    }


def detect_wsl() -> bool:
    if platform.system() != "Linux":
        return False
    for p in (Path("/proc/version"), Path("/proc/sys/kernel/osrelease")):
        txt = read_text(p).lower()
        if "microsoft" in txt or "wsl" in txt:
            return True
    return bool(os.environ.get("WSL_DISTRO_NAME"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", help="CVAT repository root; defaults to searching upward from cwd")
    ap.add_argument("--json", action="store_true", help="Print JSON only")
    args = ap.parse_args()

    requested = Path(args.repo).expanduser() if args.repo else Path.cwd()
    repo = requested.resolve() if args.repo else find_repo(requested)

    system = platform.system()
    machine = platform.machine()
    info = {
        "probe_version": 1,
        "platform": {
            "system": system,
            "release": platform.release(),
            "machine": machine,
            "python": platform.python_version(),
            "wsl": detect_wsl(),
        },
        "repo": {"requested": str(requested), "root": str(repo) if repo else None, "valid": bool(repo)},
        "tools": {},
        "cvat": {},
        "recommendations": [],
    }

    for tool, cmd in [
        ("git", ["git", "--version"]),
        ("docker", ["docker", "--version"]),
        ("docker_compose", ["docker", "compose", "version"]),
        ("nuctl", ["nuctl", "version"]),
        ("nvidia_smi", ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]),
    ]:
        info["tools"][tool] = {"path": shutil.which(cmd[0]), **run(cmd)}

    if not repo:
        info["recommendations"].append("Run this probe from a Git-cloned CVAT repository or pass --repo <path>.")
    else:
        git_root = run(["git", "rev-parse", "--show-toplevel"], cwd=repo)
        branch = run(["git", "branch", "--show-current"], cwd=repo)
        commit = run(["git", "rev-parse", "HEAD"], cwd=repo)
        status = run(["git", "status", "--porcelain"], cwd=repo)
        serverless_compose_candidates = [
            repo / "components" / "serverless" / "docker-compose.serverless.yml",
            repo / "docker-compose.serverless.yml",
        ]
        compose = next((p for p in serverless_compose_candidates if p.exists()), None)
        compose_text = read_text(compose) if compose else ""
        nuclio = parse_nuclio_image(compose_text)

        function_yamls = list((repo / "serverless").glob("**/nuclio/function.yaml")) if (repo / "serverless").exists() else []
        info["cvat"] = {
            "git_root": git_root.get("stdout") or str(repo),
            "branch": branch.get("stdout"),
            "commit": commit.get("stdout"),
            "dirty": bool(status.get("stdout")),
            "docker_compose_file": str(repo / "docker-compose.yml") if (repo / "docker-compose.yml").exists() else None,
            "serverless_compose_file": str(compose) if compose else None,
            "serverless_dir": str(repo / "serverless") if (repo / "serverless").exists() else None,
            "builtin_function_count": len(function_yamls),
            "nuclio": nuclio,
        }

        if not compose:
            info["recommendations"].append("No serverless Compose file found; inspect this CVAT revision before attempting Nuclio integration.")
        if not info["tools"]["docker_compose"]["ok"]:
            info["recommendations"].append("Install/start Docker with Compose v2 before deployment.")
        if nuclio.get("version") and not info["tools"]["nuctl"]["ok"]:
            info["recommendations"].append(
                f"Install nuctl matching the repository's Nuclio dashboard version ({nuclio['version']}); do not guess a version."
            )
        if system == "Darwin" and machine.lower() in {"arm64", "aarch64"} and nuclio.get("image_arch") == "amd64":
            info["recommendations"].append(
                "Apple Silicon detected with an amd64 Nuclio dashboard image. Confirm Docker emulation works; prefer CPU or a sidecar unless the model has arm64 support."
            )
        if info["platform"]["wsl"]:
            info["recommendations"].append(
                "WSL detected. Keep the CVAT repo inside the Linux filesystem for better Docker I/O; verify Docker Desktop WSL integration and NVIDIA WSL support if using GPU."
            )

    if args.json:
        print(json.dumps(info, indent=2))
        return

    print("CVAT MODEL INTEGRATION ENVIRONMENT")
    print("=" * 34)
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
