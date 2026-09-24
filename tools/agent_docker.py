#!/usr/bin/env python3
"""Rà soát container Docker: cái nào thuộc dự án này, cái nào là rác.

    python tools/agent_docker.py                 # CHỈ BÁO CÁO (mặc định, không xoá gì)
    python tools/agent_docker.py --json          # kèm JSON thô
    python tools/agent_docker.py --prune --yes   # xoá container đã Exited + volume/image mồ côi

Vì sao có file này
------------------
Máy chạy nhiều thứ chồng nhau: CVAT ở `D:\\DockerData\\Cvat\\cvat-day2` (compose
project `cvat`, 19 container), model-service của repo này (compose project
`cvat-browser-agent_v2`), và các function nuclio. "Dọn container lạ" không thể làm
bằng cách đoán theo tên — phải phân loại theo **nhãn compose** và **network**.

Nguyên tắc an toàn: mặc định **không xoá gì**. Container đang chạy không bao giờ bị
đụng tới, kể cả khi bị coi là lạ. Muốn xoá phải gõ `--prune --yes`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

#: Compose project của repo này (đọc từ nhãn container).
OWN_PROJECT = "cvat-browser-agent_v2"
#: Các thành phần thuộc hệ CVAT/nuclio mà dự án này phụ thuộc — không phải "lạ".
CVAT_PROJECT = "cvat"


def docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def docker_json(*args: str) -> list[dict]:
    completed = docker(*args, "--format", "json")
    if completed.returncode != 0:
        raise SystemExit(
            f"docker {' '.join(args)} lỗi:\n{completed.stderr.strip()[:400]}\n"
            "Nếu thấy 'permission denied ... npipe' thì đang bị sandbox chặn Docker API."
        )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip().startswith("{")]


def labels_of(item: dict) -> dict[str, str]:
    """`docker ps --format json` trả Labels là CHUỖI 'k=v,k=v', không phải object."""
    raw = item.get("Labels")
    if isinstance(raw, dict):
        return raw
    result: dict[str, str] = {}
    for pair in str(raw or "").split(","):
        key, _, value = pair.partition("=")
        if key.strip():
            result[key.strip()] = value.strip()
    return result


def inventory() -> dict:
    containers = docker_json("ps", "-a")
    return {
        "containers": containers,
        "volumes": docker_json("volume", "ls"),
        "images": docker_json("images"),
        "networks": docker_json("network", "ls"),
    }


def classify(containers: list[dict]) -> dict[str, list[dict]]:
    """Chia container thành: của repo, của hệ CVAT/nuclio, và ngoài dự án."""
    groups: dict[str, list[dict]] = {
        OWN_PROJECT: [],
        CVAT_PROJECT: [],
        "nuclio-function": [],
        "ngoài-dự-án": [],
    }
    for item in containers:
        labels = labels_of(item)
        project = labels.get("com.docker.compose.project", "")
        name = str(item.get("Names") or item.get("names") or "")
        if project == OWN_PROJECT:
            groups[OWN_PROJECT].append(item)
        elif project == CVAT_PROJECT:
            groups[CVAT_PROJECT].append(item)
        elif name.startswith("nuclio-"):
            # Function nuclio do dashboard sinh ra, không có nhãn compose. Tên image
            # theo quy ước `<tên>:latest` -> container `nuclio-nuclio-<tên>`.
            groups["nuclio-function"].append(item)
        else:
            groups["ngoài-dự-án"].append(item)
    return groups


def used_volume_names() -> set[str]:
    """Tên volume đang được container dùng, lấy từ `docker inspect`.

    KHÔNG suy từ `docker ps --format json`: trường Mounts ở đó bị cắt ngắn và
    không đáng tin — bản đầu của hàm này vì thế báo nhầm 13 volume "mồ côi" trong
    khi chúng đang được dùng (ví dụ `cvat-browser-agent_v2_model-hf-cache`).
    """
    ids = docker("ps", "-aq")
    if ids.returncode != 0 or not ids.stdout.strip():
        return set()
    completed = docker("inspect", *ids.stdout.split())
    if completed.returncode != 0:
        return set()
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return set()
    names: set[str] = set()
    for container in payload:
        for mount in container.get("Mounts") or []:
            if mount.get("Type") == "volume" and mount.get("Name"):
                names.add(mount["Name"])
    return names


def garbage(containers: list[dict], volumes: list[dict], images: list[dict]) -> dict[str, list]:
    exited = [
        item
        for item in containers
        if str(item.get("State", "")).lower() in {"exited", "dead", "created"}
    ]
    in_use = used_volume_names()
    orphan_volumes = [v for v in volumes if v.get("Name") not in in_use]
    dangling_images = [i for i in images if str(i.get("Repository")) == "<none>"]
    return {
        "container đã dừng": exited,
        "volume không container nào dùng": orphan_volumes,
        "image không tag": dangling_images,
        "_in_use": sorted(in_use),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--prune", action="store_true", help="xoá rác (cần --yes)")
    parser.add_argument("--yes", action="store_true", help="xác nhận thật sự muốn xoá")
    args = parser.parse_args()

    data = inventory()
    groups = classify(data["containers"])
    junk = garbage(data["containers"], data["volumes"], data["images"])

    print(f"Tổng: {len(data['containers'])} container, {len(data['volumes'])} volume, "
          f"{len(data['images'])} image\n")

    for label, items in groups.items():
        print(f"== {label}: {len(items)}")
        for item in items:
            name = item.get("Names") or item.get("names")
            state = item.get("State")
            image = item.get("Image")
            print(f"   {name:30} {state:9} {image}")
        print()

    print("== rác ==")
    for label, items in junk.items():
        if label.startswith("_"):
            continue
        print(f"   {label}: {len(items)}")
        for item in items[:15]:
            name = item.get("Names") or item.get("Name") or item.get("ID")
            print(f"      {name}")
    print(f"   (volume đang dùng: {len(junk['_in_use'])})")
    print()

    outside = groups["ngoài-dự-án"]
    if outside:
        print(f"⚠️  {len(outside)} container KHÔNG thuộc dự án này cũng không thuộc hệ CVAT/nuclio:")
        for item in outside:
            print(f"      {item.get('Names')}  image={item.get('Image')}")
    else:
        print("✅ Không có container nào nằm ngoài dự án và ngoài hệ CVAT/nuclio.")

    if args.json:
        print(json.dumps({"groups": {k: len(v) for k, v in groups.items()}, "junk": {k: len(v) for k, v in junk.items()}}, ensure_ascii=False, indent=2))

    if not args.prune:
        print("\n(Chỉ báo cáo. Thêm --prune --yes để xoá container đã dừng + volume/image mồ côi.)")
        return 0

    if not args.yes:
        print("\nTỪ CHỐI: --prune cần --yes để xác nhận.", file=sys.stderr)
        return 2

    removed = 0
    for item in junk["container đã dừng"]:
        container_id = item.get("ID")
        result = docker("rm", str(container_id))
        print(f"rm container {container_id}: {'OK' if result.returncode == 0 else result.stderr.strip()[:120]}")
        removed += result.returncode == 0
    for item in junk["volume không container nào dùng"]:
        name = item.get("Name")
        result = docker("volume", "rm", str(name))
        print(f"rm volume {name}: {'OK' if result.returncode == 0 else result.stderr.strip()[:120]}")
        removed += result.returncode == 0
    print(f"\nđã xoá {removed} mục.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
