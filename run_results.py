"""Run official results: object detection (BBox) + drivable area (Polygon).

Single entry point for producing pre-annotation results over a folder of
images. For each image it calls the running model-service:

  - POST /detect            -> YOLO26 BBox (guideline object classes)
  - POST /segment-drivable  -> EoMT drivable-area polygons

and writes annotated previews, contact sheets, raw JSON and a Markdown
report under `results/`.

Usage:
    python run_results.py                     # runs over test/detect/*.jpg
    python run_results.py --images path/to/images
    python run_results.py --out results/run_my_dataset
    python run_results.py --semantic          # also collect /segment-semantic (raw JSON only)

Requires only stdlib + Pillow + numpy on the host. The model-service itself
must already be running (see README.md, `docker compose up -d model-service`).
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
BASE_URL = "http://127.0.0.1:8001"

# Preview colours come from `taxonomy.yaml` through the generated runtime
# artifact, so renaming or adding a class never needs a change in this file.
TAXONOMY_PATH = ROOT / "model-service" / "taxonomy.json"
if not TAXONOMY_PATH.is_file():
    raise SystemExit(
        f"missing {TAXONOMY_PATH.relative_to(ROOT)}; "
        "run: python tools/sync_taxonomy.py --write"
    )
TAXONOMY = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def _colors(task: str, alpha: int | None = None) -> dict[str, tuple[int, ...]]:
    palette = TAXONOMY["tasks"][task]["colors"]
    if alpha is None:
        return {name: tuple(rgb) for name, rgb in palette.items()}
    return {name: (*rgb, alpha) for name, rgb in palette.items()}


# Detection class -> preview color (RGB).
BBOX_COLORS = _colors("bbox")
DEFAULT_BBOX_COLOR = (0, 255, 0)

# Drivable-area class -> overlay color (RGBA).
DRIVABLE_COLORS = _colors("drivable", alpha=150)
DEFAULT_DRIVABLE_COLOR = (255, 255, 255, 150)


def load_font(size: int):
    for name in ("segoeui.ttf", "arial.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _post(endpoint: str, image_path: Path, extra_fields: dict | None = None) -> dict:
    """POST one image to the model-service and return parsed JSON + latency."""
    boundary = "----dsh" + uuid.uuid4().hex
    data = image_path.read_bytes()
    fields = [("image", image_path.name)]
    for key, value in (extra_fields or {}).items():
        fields.append((key, str(value)))

    body = bytearray()
    for key, filename in fields:
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{key}"'.encode()
        if key == "image":
            body += f'; filename="{filename}"\r\n'.encode()
            body += b"Content-Type: image/jpeg\r\n\r\n"
            body += data
        else:
            body += b"\r\n\r\n"
            body += filename.encode()
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    payload["_latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return payload


def render_bbox(image_path: Path, detections: list[dict], out_path: Path) -> None:
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = load_font(16)
    for d in detections:
        x1, y1, x2, y2 = d["bbox"]
        label, conf = d["label"], d.get("confidence", 0.0)
        color = BBOX_COLORS.get(label, DEFAULT_BBOX_COLOR)
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        txt = f"{label} {conf:.2f}"
        tw, th = draw.textbbox((0, 0), txt, font=font)[2:]
        ty = max(0, y1 - th - 4)
        draw.rectangle([x1, ty, x1 + tw + 4, ty + th + 4], fill=color)
        draw.text((x1 + 2, ty + 2), txt, fill=(255, 255, 255), font=font)
    img.save(out_path, quality=92)


def render_drivable(image_path: Path, drivable: list[dict], out_path: Path) -> None:
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    for seg in drivable:
        label = seg.get("label", "?")
        color = DRIVABLE_COLORS.get(label, DEFAULT_DRIVABLE_COLOR)
        for polygon in seg.get("polygons", []):
            pts = [(polygon[i], polygon[i + 1]) for i in range(0, len(polygon) - 1, 2)]
            if len(pts) >= 3:
                draw.polygon(pts, fill=color, outline=(255, 255, 255, 255))
    img.save(out_path, quality=90)


def build_contact_sheet(images: list[Path], out_path: Path, cols: int = 5) -> None:
    thumb_w = 420
    pad = 12
    thumbs = []
    for p in images:
        img = Image.open(p).convert("RGB")
        ratio = thumb_w / img.width
        thumbs.append(img.resize((thumb_w, int(img.height * ratio))))

    rows = (len(thumbs) + cols - 1) // cols
    cell_h = max(t.height for t in thumbs) if thumbs else 0
    sheet = Image.new(
        "RGB",
        (cols * thumb_w + (cols + 1) * pad, rows * cell_h + (rows + 1) * pad),
        (30, 30, 30),
    )
    for i, thumb in enumerate(thumbs):
        r, c = divmod(i, cols)
        sheet.paste(thumb, (pad + c * (thumb_w + pad), pad + r * (cell_h + pad)))
    sheet.save(out_path, quality=88)


def write_report(out: Path, detect_rows: list[dict], drivable_rows: list[dict],
                 semantic_rows: list[dict], images_count: int) -> None:
    from collections import Counter

    class_counter: Counter = Counter()
    drivable_counter: Counter = Counter()
    for r in detect_rows:
        if not r.get("ok"):
            continue
        for d in r.get("detections", []):
            class_counter[d["label"]] += 1
    for r in drivable_rows:
        if not r.get("ok"):
            continue
        for seg in r.get("drivable", []):
            drivable_counter[seg["label"]] += 1

    lines = [
        "# Official results — pre-annotation run",
        "",
        f"- Ảnh đầu vào: **{images_count}**",
        f"- Endpoint `/detect` (YOLO26 BBox): OK {sum(1 for r in detect_rows if r.get('ok'))}/{images_count}",
        f"- Endpoint `/segment-drivable` (EoMT Polygon): OK {sum(1 for r in drivable_rows if r.get('ok'))}/{images_count}",
        f"- Semantic `/segment-semantic`: {'đã thu thập' if semantic_rows else 'bỏ qua'}",
        "",
        "## Phân bố class BBox (sau lọc guideline)",
        "",
        "| Class | Số lượng |",
        "|---|---:|",
    ]
    for cls, n in class_counter.most_common():
        lines.append(f"| {cls} | {n} |")
    lines += [
        "",
        "## Phân bố drivable area",
        "",
        "| Label | Số segment |",
        "|---|---:|",
    ]
    for cls, n in drivable_counter.most_common():
        lines.append(f"| {cls} | {n} |")
    lines += [
        "",
        "## Chi tiết từng ảnh",
        "",
        "| Ảnh | BBox | Drivable | Detect latency (ms) |",
        "|---|---:|---:|---:|",
    ]
    drivable_by_file = {r["file"]: r for r in drivable_rows}
    for r in detect_rows:
        dr = drivable_by_file.get(r["file"], {})
        lines.append(
            f"| {r['file']} | {r.get('num_guideline', 0)} | {len(dr.get('drivable', []))} | {r.get('latency_ms', '-')} |"
        )
    lines += [
        "",
        "## Artifacts",
        "",
        "- `detect.json` — toàn bộ kết quả BBox",
        "- `drivable.json` — toàn bộ kết quả drivable area",
        "- `summary.json` — tóm tắt tổng hợp",
        "- `previews/detect/*.jpg` — preview BBox từng ảnh",
        "- `previews/drivable/*.jpg` — preview drivable từng ảnh",
        "- `contact_sheet_detect.jpg` / `contact_sheet_drivable.jpg` — bảng tổng hợp",
        "",
        "> **Giới hạn đã biết (không phải lỗi):**",
        "> - `rider` chưa phân biệt được với `person` (COCO không có thuộc tính \"đang cưỡi\").",
        "> - `traffic sign` chỉ phủ `stop sign`.",
        "> - Drivable area được xấp xỉ từ `road`→`area/drivable`, `pavement-merged`→`area/alternative`.",
        "> - **Lane marking (`lane/*`) không được sinh ra** — COCO-panoptic không có class `lane/*`.",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run official pre-annotation results")
    parser.add_argument("--images", default=str(ROOT / "test" / "detect"),
                        help="Folder of .jpg images (default: test/detect)")
    parser.add_argument("--out", default=str(ROOT / "results"),
                        help="Output folder (default: results/)")
    parser.add_argument("--semantic", action="store_true",
                        help="Also collect /segment-semantic raw JSON (no preview)")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.45)
    args = parser.parse_args()

    images_dir = Path(args.images)
    out = Path(args.out)
    (out / "previews" / "detect").mkdir(parents=True, exist_ok=True)
    (out / "previews" / "drivable").mkdir(parents=True, exist_ok=True)

    images = sorted(images_dir.glob("*.jpg"))
    if not images:
        print(f"ERROR: no .jpg images in {images_dir}")
        return

    print(f"Found {len(images)} images in {images_dir}")
    detect_rows, drivable_rows, semantic_rows = [], [], []
    detect_previews, drivable_previews = [], []

    for i, p in enumerate(images, 1):
        # --- detect ---
        try:
            r = _post("/detect", p, {"conf": args.conf, "iou": args.iou})
            dets = r.get("detections", [])
            detect_rows.append({
                "file": p.name, "ok": True, "latency_ms": r["_latency_ms"],
                "raw_count": r.get("raw_count"), "num_guideline": len(dets),
                "detections": dets, "model": r.get("model"), "device": r.get("device"),
            })
            prev = out / "previews" / "detect" / f"{p.stem}.jpg"
            render_bbox(p, dets, prev)
            detect_previews.append(prev)
        except Exception as exc:
            detect_rows.append({"file": p.name, "ok": False, "error": str(exc)})

        # --- drivable ---
        try:
            r = _post("/segment-drivable", p)
            dr = r.get("drivable", [])
            drivable_rows.append({
                "file": p.name, "ok": True, "latency_ms": r["_latency_ms"],
                "raw_segment_count": r.get("raw_segment_count"),
                "drivable": dr,
                "backend": r.get("backend"), "memory": r.get("memory"),
            })
            prev = out / "previews" / "drivable" / f"{p.stem}.jpg"
            render_drivable(p, dr, prev)
            drivable_previews.append(prev)
        except Exception as exc:
            drivable_rows.append({"file": p.name, "ok": False, "error": str(exc)})

        # --- semantic (optional) ---
        if args.semantic:
            try:
                r = _post("/segment-semantic", p)
                semantic_rows.append({"file": p.name, "ok": True, "masks": r.get("masks", []),
                                      "backend": r.get("backend")})
            except Exception as exc:
                semantic_rows.append({"file": p.name, "ok": False, "error": str(exc)})

        d_ok = detect_rows[-1].get("ok")
        dr_ok = drivable_rows[-1].get("ok")
        print(f"[{i}/{len(images)}] {p.name}: bbox={len(detect_rows[-1].get('detections', [])) if d_ok else 'ERR'}"
              f" drivable={len(drivable_rows[-1].get('drivable', [])) if dr_ok else 'ERR'}")

    # --- contact sheets ---
    build_contact_sheet(detect_previews, out / "contact_sheet_detect.jpg")
    build_contact_sheet(drivable_previews, out / "contact_sheet_drivable.jpg")

    # --- persist ---
    (out / "detect.json").write_text(json.dumps(detect_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "drivable.json").write_text(json.dumps(drivable_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    if semantic_rows:
        (out / "semantic.json").write_text(json.dumps(semantic_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "images": len(images),
        "detect_ok": sum(1 for r in detect_rows if r.get("ok")),
        "detect_total": sum(r.get("num_guideline", 0) for r in detect_rows),
        "drivable_ok": sum(1 for r in drivable_rows if r.get("ok")),
        "drivable_total": sum(len(r.get("drivable", [])) for r in drivable_rows),
        "semantic_collected": bool(semantic_rows),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(out, detect_rows, drivable_rows, semantic_rows, len(images))

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nResults written to: {out}")


if __name__ == "__main__":
    main()
