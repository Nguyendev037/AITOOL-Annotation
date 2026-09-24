#!/usr/bin/env python
"""Worker suy luận landmark — CHẠY BẰNG PYTHON CỦA LÕI browser-use.

Vì sao tách thành tiến trình riêng: `mediapipe` chỉ có trong venv của lõi
(`D:\\browser-agent-core\\venv`), còn repo này chạy bằng python hệ thống và **không
cài được mediapipe** (PyPI bị chặn từ máy này). Thay vì nhân bản môi trường, repo
gọi worker này bằng python của lõi và nhận JSON trở lại.

Hợp đồng: chỉ trả **landmark thô** (toạ độ đã chuẩn hoá 0..1). Mọi suy luận về
lược đồ guideline nằm ở `browser_agent.vision.landmarks` trong repo, để chỉ có một
chỗ duy nhất quyết định point ID / trạng thái.

    python worker_landmarks.py --image a.jpg --out result.json [--rotate auto|0|90|180|270]

Kết quả JSON::

    {"ok": true, "width": 960, "height": 540, "rotation": 90,
     "pose": [{"index":0,"x":..,"y":..,"z":..,"visibility":..}, ...],
     "face": [{"index":0,"x":..,"y":..}, ...],
     "notes": ["..."]}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _fail(out: Path | None, message: str, code: int = 2) -> int:
    payload = {"ok": False, "error": message, "pose": [], "face": [], "notes": []}
    if out is not None:
        out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"ERROR: {message}", file=sys.stderr)
    return code


def _run_once(rgb, runner, *, want_face: bool):
    """Suy luận một lần qua ``MediaPipeRunner`` (tự chọn API solutions/Tasks)."""
    pose_result = runner.detect_pose(rgb)
    pose = [
        {
            "index": p.index,
            "x": p.x,
            "y": p.y,
            "z": p.z,
            "visibility": p.visibility,
            "presence": p.presence,
        }
        for p in pose_result.landmarks
    ]
    quality = 0.0
    if pose:
        visibilities = [p["visibility"] for p in pose]
        quality = sum(1 for v in visibilities if v > 0.5) / max(len(visibilities), 1)

    face = []
    if want_face:
        face_result = runner.detect_face(rgb)
        face = [
            {"index": p.index, "x": p.x, "y": p.y, "z": p.z}
            for p in face_result.landmarks
        ]

    return pose, face, quality


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--out", default=None, help="ghi JSON ra file này")
    parser.add_argument(
        "--rotate",
        default="auto",
        help="auto | 0 | 90 | 180 | 270 — auto thử 4 hướng và chọn hướng tốt nhất",
    )
    parser.add_argument("--no-face", action="store_true", help="bỏ FaceMesh (nhanh hơn)")
    args = parser.parse_args()

    out = Path(args.out) if args.out else None
    image_path = Path(args.image)
    if not image_path.is_file():
        return _fail(out, f"không thấy ảnh {image_path}")

    try:
        import cv2
    except ModuleNotFoundError as exc:
        return _fail(out, f"thiếu thư viện trong venv lõi: {exc.name}")

    # Worker chạy được với CẢ mediapipe 0.10.x (`solutions`) và 1.x (Tasks API):
    # `MediaPipeRunner` tự chọn. Trước đây worker đòi thẳng `mp.solutions`, nên
    # trên máy cài 1.x nó chỉ báo lỗi và không ai kiểm lại được kết quả landmark.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from browser_agent.vision.mediapipe_pose import MediaPipeRunner, MediaPipeUnavailable

    runner = MediaPipeRunner(enable_face=not args.no_face)
    try:
        api = runner.api
    except MediaPipeUnavailable as exc:
        return _fail(out, str(exc))

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        return _fail(out, f"cv2 không đọc được ảnh {image_path}")

    notes: list[str] = []
    if args.rotate == "auto":
        # Guideline HumanPose-17 mục 1.1: "Ảnh bị xoay 90°... mỗi lần mở ảnh mới,
        # nhìn xác định đâu là đầu đâu là chân". Máy cũng phải làm vậy: thử 4
        # hướng và chọn hướng mà model thấy được nhiều khớp nhất. Đây là suy luận
        # hình học, không phải đoán theo tên điểm.
        candidates = (0, 90, 180, 270)
    else:
        candidates = (int(args.rotate),)

    best = None
    try:
        for angle in candidates:
            rotated = image if angle == 0 else cv2.rotate(image, _rotate_code(cv2, angle))
            rgb = cv2.cvtColor(rotated, cv2.COLOR_BGR2RGB)
            pose, face, quality = _run_once(rgb, runner, want_face=not args.no_face)
            if best is None or quality > best["quality"]:
                best = {
                    "angle": angle,
                    "pose": pose,
                    "face": face,
                    "quality": quality,
                    "shape": (rotated.shape[1], rotated.shape[0]),
                }
    finally:
        runner.close()

    assert best is not None
    if len(candidates) > 1:
        notes.append(
            f"auto-rotate chọn {best['angle']}° (chất lượng {best['quality']:.2f}); "
            f"đã thử {', '.join(str(a) for a in candidates)}"
        )
    if not best["pose"]:
        notes.append("Pose không thấy người trong ảnh ở mọi hướng đã thử")
    if not best["face"] and not args.no_face:
        notes.append("FaceMesh không thấy khuôn mặt")

    payload = {
        "ok": True,
        "image": str(image_path),
        "width": best["shape"][0],
        "height": best["shape"][1],
        "rotation": best["angle"],
        "mediapipe": _mediapipe_version(),
        "api": api,
        "pose": best["pose"],
        "face": best["face"],
        "notes": notes,
    }
    text = json.dumps(payload, ensure_ascii=False)
    if out is not None:
        out.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


def _mediapipe_version() -> str:
    try:
        import mediapipe as mp

        return getattr(mp, "__version__", "?")
    except ModuleNotFoundError:  # pragma: no cover
        return "?"


def _rotate_code(cv2, angle: int):
    return {
        90: cv2.ROTATE_90_CLOCKWISE,
        180: cv2.ROTATE_180,
        270: cv2.ROTATE_90_COUNTERCLOCKWISE,
    }[angle]


if __name__ == "__main__":
    sys.exit(main())
