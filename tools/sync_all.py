#!/usr/bin/env python3
"""Một lệnh duy nhất: đồng bộ lại toàn bộ guideline + label khi `guildlline/` đổi.

    python tools/sync_all.py            # đồng bộ (mặc định)
    python tools/sync_all.py --check    # chỉ báo lệch, không ghi
    python tools/sync_all.py --status   # xem file nguồn nào đã đổi so với lần sync trước
    python tools/sync_all.py --force    # bỏ qua cache, trích xuất lại từ đầu

Vì sao có file này
------------------
Trước đây muốn cập nhật label sau khi sửa tài liệu gốc phải làm tay nhiều bước:
trích PDF -> viết lại `guideline/*.md` -> sửa `taxonomy.yaml` -> chạy
`tools/sync_taxonomy.py --write`. Bước nào quên là label lệch âm thầm.

Nay chỉ cần bỏ tài liệu mới/sửa vào `guildlline/` rồi chạy đúng một lệnh này.
Pipeline tự: phát hiện file đổi (theo sha256) -> trích xuất tất định -> sinh
`guideline/generated/*` -> cập nhật vùng sinh trong `guideline/README.md` ->
chạy `sync_taxonomy --write` -> kiểm tra lại bằng `--check` -> ghi manifest.

Điều pipeline này **không** làm: tự sửa `taxonomy.yaml`. `taxonomy.yaml` là
nguồn sự thật duy nhất cho label (xem docs/ARCHITECTURE.md); tự động ghi đè nó
từ văn bản tự do sẽ phá annotation đang có trong CVAT. Khi tài liệu gốc khai báo
label mới, pipeline báo rõ để bạn thêm vào `taxonomy.yaml`, rồi chạy lại lệnh này.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# Windows consoles default to a legacy code page (cp1252/cp437) which cannot
# encode Vietnamese text. The messages below are Vietnamese on purpose, so force
# UTF-8 before anything is printed. `errors="replace"` keeps the pipeline usable
# on terminals that still refuse the bytes.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - exotic console
            pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from sync.extract import (  # noqa: E402  (path bootstrap above)
    SourceFile,
    build_guideline_markdown,
    discover_sources,
    extraction_engine,
    extract_text,
    sha256_text,
    slugify,
)

SOURCE_DIR = ROOT / "guildlline"
GENERATED_DIR = ROOT / "guideline" / "generated"
MANIFEST = ROOT / "guideline" / ".sync-manifest.json"
GUIDELINE_README = ROOT / "guideline" / "README.md"

README_BEGIN = "<!-- BEGIN GENERATED SOURCES -->"
README_END = "<!-- END GENERATED SOURCES -->"

TAXONOMY_SCRIPT = ROOT / "tools" / "sync_taxonomy.py"


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
def load_manifest() -> dict:
    if not MANIFEST.is_file():
        return {"version": 1, "sources": {}, "outputs": {}}
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"WARN: {MANIFEST.name} hỏng, coi như chưa sync lần nào", file=sys.stderr)
        return {"version": 1, "sources": {}, "outputs": {}}
    data.setdefault("sources", {})
    data.setdefault("outputs", {})
    return data


def save_manifest(manifest: dict) -> None:
    manifest["synced_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def classify(sources: list[SourceFile], manifest: dict) -> list[tuple[SourceFile, str]]:
    """Tag each source as new / changed / unchanged relative to the manifest."""
    known = manifest.get("sources", {})
    result: list[tuple[SourceFile, str]] = []
    for source in sources:
        previous = known.get(source.rel)
        if not previous:
            state = "new"
        elif previous.get("sha256") != source.digest:
            state = "changed"
        else:
            state = "unchanged"
        result.append((source, state))
    return result


# --------------------------------------------------------------------------- #
# generated outputs
# --------------------------------------------------------------------------- #
def render_readme_region(rows: list[tuple[SourceFile, str]], outputs: dict[str, str]) -> str:
    lines = [
        README_BEGIN,
        "",
        "### Tài liệu nguồn và bản trích xuất tự động",
        "",
        "Sinh bởi `python tools/sync_all.py`. Đừng sửa tay vùng này.",
        "",
        "| Tài liệu nguồn (`guildlline/`) | sha256 | Trạng thái | Bản trích xuất |",
        "|---|---|---|---|",
    ]
    for source, state in rows:
        label = {"new": "mới", "changed": "đã đổi", "unchanged": "không đổi"}[state]
        produced = outputs.get(source.rel, "")
        target = f"[`{produced}`]({produced})" if produced else "—"
        lines.append(f"| `{source.rel}` | `{source.digest[:12]}` | {label} | {target} |")
    lines += ["", README_END]
    return "\n".join(lines)


def update_readme_region(region: str, *, write: bool) -> str | None:
    """Return a drift description when the README region is stale."""
    if not GUIDELINE_README.is_file():
        return None
    text = GUIDELINE_README.read_text(encoding="utf-8")
    if README_BEGIN in text and README_END in text:
        head, rest = text.split(README_BEGIN, 1)
        _, tail = rest.split(README_END, 1)
        updated = f"{head}{region}{tail}"
    else:
        updated = text.rstrip() + "\n\n" + region + "\n"

    if updated == text:
        return None
    if write:
        GUIDELINE_README.write_text(updated, encoding="utf-8")
        return None
    return GUIDELINE_README.relative_to(ROOT).as_posix()


# --------------------------------------------------------------------------- #
# taxonomy
# --------------------------------------------------------------------------- #
def taxonomy_code(*, check_only: bool) -> int:
    """Chạy `sync_taxonomy` ở chế độ đọc hoặc ghi.

    Tham số tên là `check_only` chứ không phải `write` có chủ ý: đọc nhầm một
    biến `write` là đúng cách mà `--check` từng ghi file.
    """
    flag = "--check" if check_only else "--write"
    completed = subprocess.run(
        [sys.executable, str(TAXONOMY_SCRIPT), flag],
        cwd=ROOT,
        text=True,
        # encoding tường minh: mặc định trên Windows là cp1252 và sẽ chết khi tiến
        # trình con in tiếng Việt (đã gặp thật ở chỗ khác: UnicodeDecodeError).
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    output = (completed.stdout + completed.stderr).strip()
    if output:
        print(output)
    return completed.returncode


def dry_run(sources: list[SourceFile], tagged, *, needs_work: bool) -> list[str]:
    """Liệt kê artifact sẽ phải ghi, **không mở file nào để ghi**.

    Đây là điều kiện để `--check` nói được lệch ở đâu. Cố ý không tạo thư mục
    `guideline/generated/`: `mkdir` cũng là ghi, dù file còn chưa có nội dung.

    Vùng sinh trong `guideline/README.md` được kiểm **luôn**, kể cả khi tài liệu
    nguồn không đổi: bản đầu của hàm này trả về sớm khi nguồn không đổi, nên sửa
    tay vùng đó xong chạy `--check` vẫn báo "OK" — đúng loại kiểm tra luôn xanh
    mà vô dụng.
    """
    stale: list[str] = []

    outputs = {
        source.rel: (GENERATED_DIR / f"{slugify(Path(source.rel).stem)}.md")
        .relative_to(ROOT)
        .as_posix()
        for source in sources
    }
    outputs["*"] = (GENERATED_DIR / "guidelines.md").relative_to(ROOT).as_posix()

    if needs_work:
        bodies: dict[str, str] = {}
        for source in sources:
            try:
                bodies[source.rel] = extract_text(source)
            except RuntimeError:
                # `--check` không được đổ vì một file nguồn hỏng: phần còn lại
                # vẫn phải báo được. Lần chạy thật sẽ dừng và báo lỗi rõ ràng.
                bodies = {}
                break
        if bodies:
            combined = build_guideline_markdown(sources, bodies)
            combined_path = GENERATED_DIR / "guidelines.md"
            actual = (
                combined_path.read_text(encoding="utf-8") if combined_path.is_file() else None
            )
            if actual != combined:
                stale.append(combined_path.relative_to(ROOT).as_posix())

            for source in sources:
                path = GENERATED_DIR / f"{slugify(Path(source.rel).stem)}.md"
                body = (
                    f"<!-- GENERATED from guildlline/{source.rel} "
                    f"(sha256 {source.digest}, engine {extraction_engine(source)}) -->\n\n"
                    + bodies[source.rel]
                    + "\n"
                )
                actual = path.read_text(encoding="utf-8") if path.is_file() else None
                if actual != body:
                    stale.append(path.relative_to(ROOT).as_posix())

    region_drift = update_readme_region(render_readme_region(tagged, outputs), write=False)
    if region_drift:
        stale.append(region_drift)
    return stale


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="chỉ báo lệch, không ghi gì")
    mode.add_argument("--status", action="store_true", help="chỉ liệt kê file nguồn đã đổi")
    parser.add_argument("--force", action="store_true", help="trích xuất lại dù nguồn không đổi")
    parser.add_argument("--quiet", action="store_true", help="chỉ in cảnh báo và lỗi")
    args = parser.parse_args()

    def log(message: str) -> None:
        if not args.quiet:
            print(message)

    if not SOURCE_DIR.is_dir():
        print(f"ERROR: không thấy thư mục nguồn {SOURCE_DIR}", file=sys.stderr)
        return 2

    sources = discover_sources(SOURCE_DIR)
    if not sources:
        print(f"ERROR: {SOURCE_DIR} không có file .pdf/.docx nào", file=sys.stderr)
        return 2

    manifest = load_manifest()
    tagged = classify(sources, manifest)
    changed = [(s, st) for s, st in tagged if st != "unchanged"]

    if args.status:
        if not changed:
            log("Không có tài liệu nguồn nào thay đổi kể từ lần sync trước.")
            return 0
        log("Tài liệu nguồn cần đồng bộ:")
        for source, state in changed:
            log(f"  - [{state}] {source.rel} (sha256 {source.digest[:12]})")
        return 1

    write = not args.check
    needs_work = bool(changed) or args.force

    # ------------------------------------------------------------------ #
    # --check: chỉ đọc, và trả về TRƯỚC mọi thao tác ghi.
    #
    # Vì sao phải chặn ở đây chứ không dựa vào cờ `write` rải khắp hàm: bản cũ
    # vẫn gọi `run_taxonomy(write=True)` ở nhánh "nguồn không đổi" và
    # `GENERATED_DIR.mkdir(...)` ở nhánh dưới, nên `--check` vẫn tạo thư mục và
    # ghi artifact label. Kiểm tra lệch mà lại sửa file là vô nghĩa.
    # ------------------------------------------------------------------ #
    if args.check:
        log("Chế độ --check: chỉ đọc, không ghi file nào.")
        stale = dry_run(sources, tagged, needs_work=needs_work)
        label_code = taxonomy_code(check_only=True)
        if label_code != 0:
            print(
                "\nLỆCH: artifact label không khớp taxonomy.yaml (chi tiết bên trên).",
                file=sys.stderr,
            )
        if stale:
            print("\nLỆCH: cần chạy `python tools/sync_all.py` để đồng bộ:", file=sys.stderr)
            for item in stale:
                print(f"  - {item}", file=sys.stderr)
            return 1
        if label_code != 0:
            return label_code
        log("OK: mọi artifact đã khớp nguồn.")
        return 0

    if not needs_work:
        log("Nguồn không đổi. Kiểm tra label có còn khớp không...")
        code = taxonomy_code(check_only=True)
        if code == 0:
            log("OK: guideline và label đã đồng bộ, không cần làm gì.")
            return 0
        log("Label lệch dù nguồn không đổi -> tự sinh lại artifact.")
        return taxonomy_code(check_only=False)

    if changed:
        log("Tài liệu nguồn thay đổi:")
        for source, state in changed:
            log(f"  - [{state}] {source.rel}")
    else:
        log("--force: trích xuất lại toàn bộ tài liệu nguồn.")

    # 1. deterministic extraction
    bodies: dict[str, str] = {}
    for source in sources:
        try:
            bodies[source.rel] = extract_text(source)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        log(f"  trích xuất {source.rel}: {len(bodies[source.rel])} ký tự")

    combined = build_guideline_markdown(sources, bodies)
    outputs: dict[str, str] = {}

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    combined_path = GENERATED_DIR / "guidelines.md"
    outputs["*"] = combined_path.relative_to(ROOT).as_posix()

    stale: list[str] = []
    if combined_path.is_file() and combined_path.read_text(encoding="utf-8") == combined:
        log(f"  không đổi: {combined_path.relative_to(ROOT).as_posix()}")
    else:
        stale.append(combined_path.relative_to(ROOT).as_posix())
        if write:
            combined_path.write_text(combined, encoding="utf-8")
            log(f"  ghi: {combined_path.relative_to(ROOT).as_posix()}")

    # per-source extraction, so a single changed document is reviewable alone
    for source in sources:
        path = GENERATED_DIR / f"{slugify(Path(source.rel).stem)}.md"
        body = (
            f"<!-- GENERATED from guildlline/{source.rel} "
            f"(sha256 {source.digest}, engine {extraction_engine(source)}) -->\n\n"
            + bodies[source.rel]
            + "\n"
        )
        outputs[source.rel] = path.relative_to(ROOT).as_posix()
        if path.is_file() and path.read_text(encoding="utf-8") == body:
            continue
        stale.append(path.relative_to(ROOT).as_posix())
        if write:
            path.write_text(body, encoding="utf-8")
            log(f"  ghi: {path.relative_to(ROOT).as_posix()}")

    # 2. guideline README generated region
    region = render_readme_region(tagged, outputs)
    readme_drift = update_readme_region(region, write=write)
    if readme_drift:
        stale.append(readme_drift)

    # 3. taxonomy artifacts
    log("Đồng bộ artifact label (sync_taxonomy)...")
    # Tên biến khác tên hàm: đặt trùng sẽ che mất hàm `taxonomy_code` ở trên.
    label_code = taxonomy_code(check_only=not write)

    if write:
        manifest["sources"] = {
            source.rel: {"sha256": source.digest, "size": source.size} for source in sources
        }
        manifest["outputs"] = outputs
        manifest["combined_sha256"] = sha256_text(combined)
        save_manifest(manifest)

    print()
    print("Xong. Đã đồng bộ guideline và artifact label.")
    print("Bước tiếp theo nếu có label mới trong tài liệu:")
    print("  1. thêm label vào taxonomy.yaml   (nguồn sự thật duy nhất)")
    print("  2. chạy lại: python tools/sync_all.py")
    print("  3. triển khai lại nuclio: nuclio/README.md mục 6b")
    return label_code


if __name__ == "__main__":
    sys.exit(main())
