#!/usr/bin/env python3
"""Kiểm tra kết nối CVAT và in ra cấu trúc label/annotation thật của một job.

    python tools/agent_probe.py --target local
    python tools/agent_probe.py --target online --job 1573
    python tools/agent_probe.py --target local --job 26 --show-shapes

Dùng để trả lời ba câu hỏi trước khi cho agent ghi bất cứ thứ gì:
  1. Token còn sống không, đang đăng nhập là ai.
  2. Job có label gì, skeleton có đủ sublabel theo guideline không.
  3. Annotation hiện có bao nhiêu shape, thuộc label nào, có phải pre-label không.
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
from browser_agent.cvat_rest import CvatClient, CvatError, sublabel_map  # noqa: E402
from browser_agent.geometry import (  # noqa: E402
    FACE_POINT_COUNT,
    FACE_SKELETONS,
    POSE17_LABEL_CANDIDATES,
    POSE17_SKELETON,
)


def check_skeleton_schema(label: dict, *, expected: dict[str, int]) -> list[str]:
    """So label skeleton thật với đặc tả guideline. Trả về danh sách lỗi."""
    problems: list[str] = []
    subs = sublabel_map(label)
    if str(label.get("type", "")).lower() != "skeleton":
        problems.append(f"label {label.get('name')!r} không phải type skeleton (đang là {label.get('type')})")
    if not label.get("svg"):
        problems.append(f"label {label.get('name')!r} thiếu trường svg")
    missing = sorted(set(expected) - set(subs))
    extra = sorted(set(subs) - set(expected))
    if missing:
        problems.append(f"thiếu sublabel: {', '.join(missing)}")
    if extra:
        problems.append(f"thừa sublabel: {', '.join(extra)}")
    return problems


def describe_pose_schema(labels: list[dict]) -> str:
    """Đối chiếu schema HumanPose-17 và trả về kết luận dạng chữ.

    Tách khỏi ``main`` để test được bằng payload thật đọc từ CVAT, và để không tái
    diễn lỗi cũ: ghim cứng tên ``person`` rồi im lặng không kiểm tra gì.
    """
    by_name = {str(label.get("name", "")).strip().lower(): label for label in labels}
    candidate = next((name for name in POSE17_LABEL_CANDIDATES if name in by_name), None)
    if candidate is None:
        wanted = " hoặc ".join(repr(name) for name in POSE17_LABEL_CANDIDATES)
        return (
            f"HumanPose-17: KHÔNG kiểm tra được — job không có label skeleton nào tên {wanted}"
        )
    expected = {str(pid): pid for pid in POSE17_SKELETON.point_ids}
    problems = check_skeleton_schema(by_name[candidate], expected=expected)
    lines = [f"HumanPose-17 `{candidate}`: {'KHỚP guideline' if not problems else 'LỆCH'}"]
    lines.extend(f"  - {problem}" for problem in problems)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default=None, help="local | online (mặc định: cái nào có token)")
    parser.add_argument("--job", type=int, default=None, help="job id cần soi")
    parser.add_argument("--show-shapes", action="store_true", help="in chi tiết từng shape")
    parser.add_argument("--json", action="store_true", help="in JSON thô")
    args = parser.parse_args()

    try:
        settings = resolve_cvat(args.target)
    except KeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"# {settings.describe()}")
    client = CvatClient(settings, timeout=30)
    try:
        smoke = client.smoke()
    except CvatError as exc:
        print(f"LỖI KẾT NỐI: {exc}", file=sys.stderr)
        return 3

    print(f"CVAT {smoke['version']} — đăng nhập là {smoke['user']!r} (superuser={smoke['is_superuser']})")

    if args.job is None:
        print("\nChưa có --job nên chỉ kiểm tra kết nối. Ví dụ: --job 1573")
        return 0

    job = client.job(args.job)
    task_id = job.get("task_id")
    print(f"\n## Job {args.job} (task {task_id}) — state={job.get('state')} stage={job.get('stage')}")
    print(f"   frames: {job.get('start_frame')}..{job.get('stop_frame')}")

    labels = client.job_labels(args.job)
    print(f"\n## Labels ({len(labels)})")
    for label in labels:
        subs = sublabel_map(label)
        suffix = f" sublabels={len(subs)}" if subs else ""
        print(f"   [{label.get('id')}] {label.get('name')!r} type={label.get('type')}{suffix}")
        if subs:
            print(f"        sublabels: {', '.join(sorted(subs, key=lambda s: (len(s), s)))}")

    # Đối chiếu với hai guideline của Week 2 nếu job có label tương ứng.
    by_name = {str(label.get("name", "")).strip().lower(): label for label in labels}

    print("\n   " + describe_pose_schema(labels).replace("\n", "\n   "))

    # Face Landmark: trên CVAT thật, cả bài mặt nằm trong MỘT skeleton, không phải
    # 7 label rời đặt tên theo nhóm. Vì vậy phải dò theo cả hai kiểu cấu hình, và
    # nói rõ khi có label mặt nhưng schema không khớp VF-50 thay vì im lặng bỏ qua.
    groups = {spec.name for spec in FACE_SKELETONS}
    group_labels = [name for name in by_name if name in groups]
    if group_labels:
        for name in sorted(group_labels):
            spec = next(s for s in FACE_SKELETONS if s.name == name)
            expected = {str(pid): pid for pid in spec.point_ids}
            problems = check_skeleton_schema(by_name[name], expected=expected)
            print(f"   VF-50 `{name}`:", "KHỚP guideline" if not problems else "LỆCH")
            for problem in problems:
                print(f"     - {problem}")
    else:
        numeric = [
            label
            for label in labels
            if str(label.get("type", "")).lower() == "skeleton" and sublabel_map(label)
        ]
        matching = [
            label
            for label in numeric
            if set(sublabel_map(label)) == {str(pid) for pid in range(FACE_POINT_COUNT)}
        ]
        if matching:
            for label in matching:
                problems = check_skeleton_schema(
                    label, expected={str(pid): pid for pid in range(FACE_POINT_COUNT)}
                )
                print(
                    f"   VF-50 `{label.get('name')}` (một skeleton, sublabel 0..{FACE_POINT_COUNT - 1}):",
                    "KHỚP guideline" if not problems else "LỆCH",
                )
                for problem in problems:
                    print(f"     - {problem}")
        else:
            shapes = ", ".join(
                f"{label.get('name')!r}({len(sublabel_map(label))} sublabel)" for label in numeric
            )
            print(
                "   VF-50: KHÔNG tìm thấy schema khớp. Không label nào có sublabel "
                f"'0'..'{FACE_POINT_COUNT - 1}' và cũng không có 7 label nhóm. "
                f"Skeleton số đang có: {shapes or '(không có)'}"
            )

    shapes = client.shapes(args.job)
    print(f"\n## Annotation hiện có: {len(shapes)} shape")
    counts: dict[tuple[int, str], int] = {}
    for shape in shapes:
        counts[(shape.label_id, shape.type)] = counts.get((shape.label_id, shape.type), 0) + 1
    label_names = {int(label["id"]): str(label.get("name")) for label in labels}
    for (label_id, shape_type), count in sorted(counts.items()):
        print(f"   {label_names.get(label_id, label_id)!r} ({shape_type}): {count}")
    if shapes:
        sources: dict[str, int] = {}
        for shape in shapes:
            sources[shape.source or "(trống)"] = sources.get(shape.source or "(trống)", 0) + 1
        print(f"   nguồn: {sources}")
    if args.show_shapes and shapes:
        print("\n## Chi tiết shape")
        for shape in shapes[:40]:
            print(f"   {shape.summary()}")
        if len(shapes) > 40:
            print(f"   ... còn {len(shapes) - 40} shape nữa")

    if args.json:
        print("\n## JSON thô")
        print(json.dumps(client.annotations(args.job), indent=2, ensure_ascii=False)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
