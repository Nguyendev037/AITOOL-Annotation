#!/usr/bin/env python3
"""Suy luận landmark và ghi skeleton lên CVAT ONLINE (cvat.note.transformerlabs.ai).

    # Xem thử, KHÔNG ghi
    python tools/agent_online.py --job 2214 --task face50

    # Ghi thật (mặc định append — không đụng annotation đang có)
    python tools/agent_online.py --job 2214 --task face50 --write

Vì sao tách khỏi `tools/agent_vision.py`: bản local đọc label rồi ghi trong cùng một
lần gọi; bản online phải tải ảnh frame từ server trước, và **quan trọng hơn**: trên job
này mỗi nhóm guideline là MỘT LABEL RIÊNG (`longmaytrai`, `mattrai`, …), không phải
một skeleton 50 sublabel. Nên phải ghi 7 skeleton rời, mỗi cái đúng số điểm của nhóm.

Cấu hình label đã đối chiếu trên job 2214: 8 skeleton — `person` (1..17) và 7 nhóm mặt
(`longmaytrai` 0-4, `longmayphai` 5-9, `songmui` 10-13, `mattrai` 14-21,
`matphai` 22-29, `moingoai` 30-41, `moitrong` 42-49).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover
            pass

from browser_agent.config import CvatSettings, browser_settings  # noqa: E402
from browser_agent.cvat_rest import CvatClient, CvatError, sublabel_map  # noqa: E402
from browser_agent.geometry import FACE_SKELETONS  # noqa: E402
from browser_agent.vision.pipeline import (  # noqa: E402
    SkeletonLabels,
    VisionPayloadError,
    map_payload,
    points_to_skeleton_shape,
)

WORKER = ROOT / "browser_agent" / "vision" / "worker_landmarks.py"
TOKEN_FILE = ROOT / "work" / "online_token.txt"
ONLINE_URL = "https://cvat.note.transformerlabs.ai"


def online_client() -> CvatClient:
    if not TOKEN_FILE.is_file():
        raise SystemExit(
            f"Chưa có token online. Chạy trước:\n"
            f"  python work\\online_session.py --login --username <user>\n"
            f"(token được lưu vào {TOKEN_FILE.relative_to(ROOT)})"
        )
    return CvatClient(
        CvatSettings(url=ONLINE_URL, token=TOKEN_FILE.read_text(encoding="utf-8").strip(), label="CVAT online"),
        timeout=180,
    )


def fetch_frame(client: CvatClient, job_id: int, frame: int, target: Path) -> Path:
    payload = client.frame_bytes(job_id, frame, quality="original")
    target.write_bytes(payload)
    return target


def run_worker(image: Path, *, rotate: str) -> dict:
    settings = browser_settings()
    if not settings.installed:
        raise SystemExit(f"Không thấy python của lõi tại {settings.python}")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lm.json"
        completed = subprocess.run(
            [
                str(settings.python), str(WORKER),
                "--image", str(image), "--out", str(out), "--rotate", rotate,
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
        )
        if not out.is_file():
            raise SystemExit(f"worker không trả kết quả:\n{completed.stderr[-1200:]}")
        return json.loads(out.read_text(encoding="utf-8"))


def labels_by_group(client: CvatClient, job_id: int) -> dict[str, SkeletonLabels]:
    """Map tên nhóm guideline -> label/subLabel thật của job."""
    result: dict[str, SkeletonLabels] = {}
    for label in client.job_labels(job_id):
        subs = sublabel_map(label)
        if subs:
            result[str(label.get("name", ""))] = SkeletonLabels(
                label_id=int(label["id"]), sublabels=subs
            )
    return result


def build_shapes(
    report, task: str, labels: dict[str, SkeletonLabels], frame: int
) -> list[dict]:
    """Dựng payload skeleton cho một frame.

    Bài mặt trên job này dùng **7 label rời** (mỗi nhóm guideline một label), không
    phải một skeleton 50 sublabel — nên phải tách điểm theo nhóm và ghi 7 skeleton.
    """
    shapes: list[dict] = []
    if task.startswith("face"):
        for spec in FACE_SKELETONS:
            group_labels = labels.get(spec.name)
            if group_labels is None:
                continue
            members = [p for p in report.points if p.group == spec.name]
            if not members:
                continue
            shapes.append(
                points_to_skeleton_shape(
                    members, group_labels, frame=frame, source="auto", group=len(shapes)
                )
            )
        return shapes

    target = next((name for name in ("person", "body") if name in labels), None)
    if target is None:
        return []
    return [
        points_to_skeleton_shape(report.points, labels[target], frame=frame, source="auto")
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--job", type=int, required=True)
    parser.add_argument("--task", required=True, help="face50 | pose17")
    parser.add_argument("--frame", type=int, default=0, help="frame đơn")
    parser.add_argument(
        "--frames",
        default=None,
        help="'all' hoặc danh sách '0,2,4' — chạy nhiều frame",
    )
    parser.add_argument(
        "--skip-labelled",
        action="store_true",
        help="bỏ qua frame đã có shape (mặc định BẬT khi dùng --frames)",
    )
    parser.add_argument("--rotate", default="auto")
    parser.add_argument("--write", action="store_true", help="THẬT SỰ ghi lên CVAT")
    parser.add_argument("--out", default=None, help="ghi payload ra file JSON")
    args = parser.parse_args()

    client = online_client()
    job = client.job(args.job)
    first = int(job.get("start_frame") or 0)
    last = int(job.get("stop_frame") or 0)
    print(f"job {args.job}: task={job.get('task_id')} frames {first}..{last}")
    assignee = (job.get("assignee") or {}).get("username")
    me = client.user_self().get("username")
    print(f"assignee={assignee} (bạn là {me})")
    if assignee and assignee != me:
        print("TỪ CHỐI: job này không giao cho bạn.", file=sys.stderr)
        return 5

    # Xác định danh sách frame cần chạy.
    if args.frames:
        if args.frames.strip().lower() == "all":
            targets = list(range(first, last + 1))
        else:
            targets = [int(part) for part in args.frames.split(",") if part.strip()]
    else:
        targets = [args.frame]

    existing = client.shapes(args.job)
    labelled: dict[int, int] = {}
    for shape in existing:
        labelled[shape.frame] = labelled.get(shape.frame, 0) + 1

    skip = args.skip_labelled or bool(args.frames)
    if skip:
        blocked = [f for f in targets if labelled.get(f)]
        if blocked:
            print(f"bỏ qua frame đã có shape: {blocked}")
            targets = [f for f in targets if not labelled.get(f)]
    print(f"sẽ chạy {len(targets)} frame: {targets}")
    if not targets:
        print("không còn frame nào cần làm.")
        return 0

    labels = labels_by_group(client, args.job)
    print(f"job có {len(labels)} label skeleton: {', '.join(sorted(labels))}")

    frame_dir = ROOT / "work" / "online_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    all_shapes: list[dict] = []
    failures: list[tuple[int, str]] = []

    for frame in targets:
        print(f"\n--- frame {frame} ---")
        try:
            image = fetch_frame(
                client, args.job, frame, frame_dir / f"job{args.job}_f{frame}.jpg"
            )
            payload = run_worker(image, rotate=args.rotate)
            print(
                f"  worker: pose={len(payload.get('pose') or [])} "
                f"face={len(payload.get('face') or [])}, xoay {payload.get('rotation')}°"
            )
            report, warnings = map_payload(payload, task=args.task)
            counts = report.counts()
            print(
                f"  map: {len(report.points)} điểm — visible={counts.get('visible',0)} "
                f"occluded={counts.get('occluded',0)} outside={counts.get('outside',0)}"
            )
            for warning in warnings:
                print(f"    cảnh báo: {warning}")
            shapes = build_shapes(report, args.task, labels, frame)
            if not shapes:
                failures.append((frame, "không dựng được skeleton nào"))
                continue
            print(f"  {len(shapes)} skeleton, {sum(len(s['elements']) for s in shapes)} điểm")
            all_shapes.extend(shapes)
        except (VisionPayloadError, CvatError) as exc:
            failures.append((frame, str(exc)[:200]))
            print(f"  LỖI: {exc}", file=sys.stderr)

    print(f"\ntổng: {len(all_shapes)} skeleton cho {len(targets) - len(failures)} frame")
    if failures:
        for frame, reason in failures:
            print(f"  thất bại frame {frame}: {reason}")

    if args.out:
        Path(args.out).write_text(
            json.dumps(all_shapes, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"đã ghi payload {args.out}")

    if not args.write:
        print("\nCHƯA GHI. Thêm --write để ghi thật (append, không đụng dữ liệu cũ).")
        return 0
    if not all_shapes:
        print("không có gì để ghi.", file=sys.stderr)
        return 1

    # CVAT nhận nhiều frame trong một request: mỗi shape mang `frame` riêng.
    try:
        result = client.patch_annotations(args.job, action="create", shapes=all_shapes)
    except CvatError as exc:
        print(f"LỖI ghi: {exc}", file=sys.stderr)
        return 4
    created = result.get("shapes", []) if isinstance(result, dict) else []
    print(f"\nĐÃ GHI {len(created)} skeleton lên job {args.job}.")
    per_frame: dict[int, int] = {}
    for shape in created:
        per_frame[shape.get("frame")] = per_frame.get(shape.get("frame"), 0) + 1
    for frame in sorted(per_frame):
        print(f"   frame {frame}: {per_frame[frame]} skeleton")
    return 0


if __name__ == "__main__":
    sys.exit(main())
