"""Dựng ảnh có 50 điểm + đường nối để soi bằng mắt trước khi ghi lên CVAT.

Vì sao có lệnh này: bốn lỗi landmark (mày/miệng/mũi/đường nối) tồn tại lâu vì
**không có cách nào nhìn thấy kết quả**. Reviewer phải tự mở CVAT mới phát hiện.
Lệnh này chạy đúng `MediaPipeRunner` + `map_face50` mà pipeline dùng, rồi vẽ ra PNG
kèm vùng phóng to mày / mũi / miệng và bảng toạ độ.

Ví dụ::

    python tools/preview_face_landmarks.py work/face_2214_f0.jpg
    python tools/preview_face_landmarks.py anh.jpg --out work/xem --zoom mat
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from browser_agent.geometry import FACE_SKELETONS, face_edges  # noqa: E402
from browser_agent.vision.landmarks import map_face50  # noqa: E402
from browser_agent.vision.mediapipe_pose import MediaPipeRunner  # noqa: E402

COLORS = {
    "longmaytrai": (255, 40, 40),
    "longmayphai": (255, 150, 0),
    "songmui": (0, 200, 255),
    "mattrai": (60, 255, 60),
    "matphai": (0, 120, 255),
    "moingoai": (255, 0, 255),
    "moitrong": (255, 255, 0),
}


def _zoom_boxes(width: int, height: int, point_count: int) -> dict[str, tuple[int, int, int, int]]:
    """Vùng phóng to, suy theo kích thước ảnh để chạy được với ảnh khác tỉ lệ."""
    cx, cy = width // 2, height // 2
    w = width // 6
    h = height // 6
    return {
        "brow": (cx - w, cy - h * 2, cx + w, cy - h),
        "nose": (cx - w // 2, cy - h, cx + w // 2, cy + h // 2),
        "mouth": (cx - w, cy + h // 4, cx + w, cy + h),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", type=Path, help="ảnh cần soi")
    parser.add_argument("--out", type=Path, default=None, help="tiền tố file kết quả (mặc định: cạnh ảnh)")
    parser.add_argument("--zoom", choices=("all", "mat", "none"), default="all", help="có cắt vùng phóng to không")
    parser.add_argument("--table", action="store_true", help="in bảng toạ độ từng điểm")
    args = parser.parse_args()

    if not args.image.is_file():
        print(f"KHÔNG thấy ảnh: {args.image}", file=sys.stderr)
        return 2

    try:
        from PIL import Image, ImageDraw
    except ModuleNotFoundError:
        print("Cần Pillow: python -m pip install Pillow", file=sys.stderr)
        return 2

    image = Image.open(args.image).convert("RGB")
    width, height = image.size

    runner = MediaPipeRunner()
    try:
        api = runner.api
        import numpy as np

        observation = runner.detect_face(np.asarray(image))
    finally:
        runner.close()

    print(f"ảnh {args.image.name} {width}x{height}  |  API MediaPipe: {api}")
    print(f"landmark thô: {len(observation.landmarks)}  ok={observation.ok}")
    if not observation.ok:
        print("FaceMesh KHÔNG thấy mặt trong ảnh này — không có gì để vẽ.", file=sys.stderr)
        return 1

    report = map_face50(observation, wid=width, hei=height)
    for warning in report.warnings:
        print(f"  CẢNH BÁO: {warning}")

    xy = {p.point_id: (p.x, p.y) for p in report.points}
    draw = ImageDraw.Draw(image)
    for spec in FACE_SKELETONS:
        color = COLORS[spec.name]
        for a, b in face_edges(spec):
            if a in xy and b in xy:
                draw.line([xy[a], xy[b]], fill=color, width=2)
        for point_id in spec.point_ids:
            if point_id not in xy:
                continue
            x, y = xy[point_id]
            draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=color, outline=(0, 0, 0))
            draw.text((x + 4, y - 13), str(point_id), fill=(0, 0, 0))
            draw.text((x + 3, y - 14), str(point_id), fill=(255, 255, 255))

    prefix = args.out or args.image.with_suffix("")
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    full = prefix.with_name(prefix.name + "_annotated.png")
    image.save(full)
    print(f"đã ghi {full}")

    if args.zoom != "none":
        for name, box in _zoom_boxes(width, height, len(report.points)).items():
            if args.zoom == "mat" and name not in ("brow", "mouth"):
                continue
            crop = image.crop(box)
            crop = crop.resize((crop.width * 5, crop.height * 5), Image.LANCZOS)
            target = prefix.with_name(f"{prefix.name}_zoom_{name}.png")
            crop.save(target)
            print(f"đã ghi {target}")

    if args.table:
        print("\n ID     x      y    mp   nhóm")
        for spec in FACE_SKELETONS:
            print(f"-- {spec.name}")
            for point in report.points:
                if point.group == spec.name:
                    print(f"  {point.point_id:2d} {point.x:6.0f} {point.y:6.0f} "
                          f"{str(point.mediapipe):>4}  {point.state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
