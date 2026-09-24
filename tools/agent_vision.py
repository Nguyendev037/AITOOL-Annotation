#!/usr/bin/env python3
"""Suy luận landmark cho một ảnh rồi in/ghi payload skeleton cho CVAT.

    # Ảnh local -> payload 17 điểm, chỉ in ra để soi
    python tools/agent_vision.py --task pose17 --image datasets/1354/G01_B011.jpg

    # Ghi thẳng vào một job CVAT (mặc định append, KHÔNG đụng dữ liệu đang có)
    python tools/agent_vision.py --task pose17 --target local --job 23 \
        --image frame0.jpg --write

    # Bài mặt: mỗi nhóm guideline là một skeleton (nếu task cấu hình 7 label nhóm)
    python tools/agent_vision.py --task face50 --image face.jpg --groups

Vì sao cần lệnh này: trước đây ba mảnh (suy luận landmark, map theo guideline, ghi
CVAT) nằm rời nhau nên không có cách nào chạy thật một vòng để biết đúng hay sai.
Lệnh này là đường chạy thật duy nhất, và nó mặc định **không ghi**.

Python dùng để chạy mediapipe là python của lõi browser-use
(``D:\\browser-agent-core\\venv``), vì repo không cài được mediapipe.
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

from browser_agent.config import browser_settings, resolve_cvat  # noqa: E402
from browser_agent.cvat_rest import CvatClient, CvatError, sublabel_map  # noqa: E402
from browser_agent.geometry import (  # noqa: E402
    FACE_SKELETONS,
    POSE17_LABEL_CANDIDATES,
)
from browser_agent.vision.pipeline import (  # noqa: E402
    SkeletonLabels,
    VisionPayloadError,
    expected_sublabels,
    face_group_shapes,
    map_payload,
    points_to_skeleton_shape,
)

WORKER = ROOT / "browser_agent" / "vision" / "worker_landmarks.py"


def run_worker(image: Path, *, rotate: str, no_face: bool) -> dict:
    """Gọi worker bằng python của lõi và đọc JSON trả về."""
    settings = browser_settings()
    python = settings.python
    if not python.is_file():
        raise SystemExit(
            f"Không thấy python của lõi tại {python}.\n"
            f"Đặt BROWSER_CORE_DIR trong .env, hoặc cài lõi theo browser-use/README."
        )

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "landmarks.json"
        command = [
            str(python),
            str(WORKER),
            "--image",
            str(image),
            "--out",
            str(out),
            "--rotate",
            rotate,
        ]
        if no_face:
            command.append("--no-face")
        # encoding tường minh: mặc định trên Windows là cp1252, sẽ chết khi worker
        # in thông báo tiếng Việt (đã gặp thật: UnicodeDecodeError 0x8d).
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=ROOT,
        )
        if not out.is_file():
            raise SystemExit(
                f"worker không tạo được kết quả (exit {completed.returncode}):\n"
                f"{completed.stderr[-1500:]}"
            )
        return json.loads(out.read_text(encoding="utf-8"))


def labels_for_skeleton(client: CvatClient, job_id: int, task: str) -> SkeletonLabels:
    """Tìm label skeleton khớp bài và lấy id sublabel thật."""
    labels = client.job_labels(job_id)
    wanted = expected_sublabels(task)

    candidates: list[tuple[dict, dict[str, int]]] = []
    for label in labels:
        subs = sublabel_map(label)
        if subs:
            candidates.append((label, subs))

    # Ưu tiên label có tên gợi ý đúng bài (body/person cho pose).
    preferred = {n.lower() for n in POSE17_LABEL_CANDIDATES} if task.startswith("pose") else set()
    for label, subs in candidates:
        if str(label.get("name", "")).lower() in preferred and wanted <= set(subs):
            return SkeletonLabels(label_id=int(label["id"]), sublabels=subs)

    for label, subs in candidates:
        missing = wanted - set(subs)
        if not missing:
            return SkeletonLabels(label_id=int(label["id"]), sublabels=subs)

    described = ", ".join(
        f"{label.get('name')!r}({len(subs)} sublabel)" for label, subs in candidates
    )
    raise SystemExit(
        f"Không label skeleton nào có đủ sublabel cho bài {task!r}.\n"
        f"  cần: {', '.join(sorted(wanted))}\n"
        f"  job có: {described or '(không có skeleton)'}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--task", required=True, help="pose17 | face50")
    parser.add_argument("--image", required=True, help="ảnh cần suy luận")
    parser.add_argument("--target", default=None, help="local | online")
    parser.add_argument("--job", type=int, default=None, help="job id để lấy id label")
    parser.add_argument("--frame", type=int, default=0)
    parser.add_argument("--rotate", default="auto", help="auto | 0 | 90 | 180 | 270")
    parser.add_argument("--no-face", action="store_true", help="bỏ FaceMesh")
    parser.add_argument("--write", action="store_true", help="THẬT SỰ ghi lên CVAT")
    parser.add_argument("--groups", action="store_true", help="bài mặt: tách 7 skeleton theo nhóm")
    parser.add_argument("--json", action="store_true", help="in payload JSON")
    parser.add_argument("--out", default=None, help="ghi payload ra file JSON")
    args = parser.parse_args()

    image = Path(args.image)
    payload = run_worker(image, rotate=args.rotate, no_face=args.no_face)
    try:
        report, warnings = map_payload(payload, task=args.task)
    except VisionPayloadError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2

    counts = report.counts()
    print(
        f"{len(report.points)} điểm — visible={counts.get('visible', 0)} "
        f"occluded={counts.get('occluded', 0)} outside={counts.get('outside', 0)}"
    )
    print(
        f"ảnh {payload.get('width')}x{payload.get('height')}, "
        f"xoay {payload.get('rotation')}°, mediapipe {payload.get('mediapipe')}"
    )
    for note in (payload.get("notes") or []) + warnings:
        print(f"  cảnh báo: {note}")

    if args.job is None:
        if args.json or args.out:
            body = {
                "task": args.task,
                "frame": args.frame,
                "points": [point.as_dict() for point in report.points],
                "warnings": warnings,
            }
            text = json.dumps(body, ensure_ascii=False, indent=2)
            if args.out:
                Path(args.out).write_text(text, encoding="utf-8")
                print(f"đã ghi {args.out}")
            else:
                print(text)
        else:
            print("\n(chưa có --job nên chỉ suy luận; thêm --job để dựng payload)")
        return 0

    client = CvatClient(resolve_cvat(args.target), timeout=60)
    try:
        labels = labels_for_skeleton(client, args.job, args.task)
    except CvatError as exc:
        print(f"LỖI đọc label: {exc}", file=sys.stderr)
        return 3

    if args.groups:
        by_group = {spec.name: labels for spec in FACE_SKELETONS}
        shapes = face_group_shapes(report, by_group, frame=args.frame)
    else:
        shapes = [
            points_to_skeleton_shape(report.points, labels, frame=args.frame, source="auto")
        ]

    print(f"\n{len(shapes)} shape sẵn sàng, label_id={labels.label_id}")
    if args.out:
        Path(args.out).write_text(
            json.dumps(shapes, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"đã ghi payload {args.out}")

    if not args.write:
        print("\nCHƯA GHI. Thêm --write để ghi thật (chế độ append, không đụng dữ liệu cũ).")
        if args.json:
            print(json.dumps(shapes, ensure_ascii=False, indent=2))
        return 0

    try:
        result = client.patch_annotations(args.job, action="create", shapes=shapes)
    except CvatError as exc:
        print(f"LỖI ghi: {exc}", file=sys.stderr)
        return 4
    created = len(result.get("shapes", [])) if isinstance(result, dict) else "?"
    print(f"ĐÃ GHI {created} shape lên job {args.job} (action=create).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
