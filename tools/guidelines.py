#!/usr/bin/env python3
"""Sinh + kiểm `guideline/profiles/*.yaml` từ tài liệu nguồn.

    python tools/guidelines.py generate        # sinh profile (offline, không gọi LLM)
    python tools/guidelines.py check           # kiểm profile, thoát khác 0 nếu lỗi
    python tools/guidelines.py status          # profile nào có hiệu lực, cái nào chờ

Vì sao mặc định **offline**: bước sinh chỉ cần bản trích xuất tất định đã có
trong `guideline/generated/`, nên chạy được không mạng và cho kết quả lặp lại
được. Gọi LLM chỉ để *đọc lại* văn xuôi thành YAML, mà mọi thứ cần cho một
profile hợp lệ (label, shape, dẫn chứng) đều đã nằm trong nguồn và taxonomy.

Vì sao `status` mặc định là `pending`: profile mơ hồ hoặc model không hỗ trợ
**không** được tự có hiệu lực. Chỉ profile qua sạch mọi luật kiểm mới thành
`applied`.

Vì sao không sinh profile cho bài không có tài liệu nguồn: bbox/semantic có
nguồn PDF riêng; drivable/lane chỉ là cách xấp xỉ từ COCO, không có tài liệu
chuẩn nào khai label của chúng, nên ở đây báo rõ là bỏ qua thay vì bịa dẫn chứng.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from browser_agent.guideline_profiles import (  # noqa: E402
    PROFILES_DIR,
    SOURCES_DIR,
    Profile,
    ProfileEntry,
    check_all,
    dump_profile,
    generated_markdown,
    load_profiles,
    read_source_text,
    sha256_file,
    taxonomy_index,
    validate_profile,
)

#: Bài -> tài liệu nguồn. Chỉ những bài có tài liệu thật mới sinh được profile.
TASK_SOURCES: dict[str, str] = {
    "pose17": "Week2_Guideline_HumanPose17_HocVien_v1.1.docx",
    "face50": "Week2_Guideline_Face_Landmark_VF50_HocVien_v1.3.docx",
    "bbox": "Annotation_Guideline_BBox_Polygon_Polyline.pdf",
    "semantic": "Semantic_Segmentation_Annotation_Guideline.pdf",
}


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _normalized(text: str) -> str:
    """Gộp mọi khoảng trắng thành một dấu cách.

    Cần thiết vì bảng trong PDF bị trích thành nhiều dòng: nhãn `traffic light`
    nằm vắt qua hai dòng ("... traffic light, traffic" / "sign"), nên tìm theo
    dòng sẽ báo thiếu oan.
    """
    return " ".join(text.split())


def _find_evidence(text: str, needles: tuple[str, ...]) -> str | None:
    """Dòng đầu tiên trong nguồn chứa một trong các `needles`.

    Trả về **nguyên văn dòng đó** vì luật kiểm số 6 đòi dẫn chứng phải có thật
    trong bản trích xuất. Không tìm thấy -> None, và mục đó sẽ không được sinh
    thay vì bịa một câu.
    """
    for raw in text.splitlines():
        line = raw.strip()
        if not line or len(line) < 4:
            continue
        if any(needle in line for needle in needles):
            return line
    return None


def _wrapped_label_evidence(text: str, name: str, *, window: int = 70) -> str | None:
    """Dẫn chứng cho nhãn bị bảng PDF vắt qua nhiều dòng.

    Trả về **đoạn trích nguyên văn** (đã gộp khoảng trắng) quanh nhãn, không phải
    một câu mô tả do mình viết ra. Bản đầu của hàm này chèn câu
    "(nhãn có trong nguồn nhưng bị ngắt dòng)" — câu đó không có trong nguồn nên
    bộ kiểm bắt lỗi ngay. Dẫn chứng phải là chữ của nguồn.
    """
    normalized = _normalized(text)
    start_at = 0
    while True:
        index = normalized.find(name, start_at)
        if index == -1:
            return None
        start = max(0, index - window)
        end = min(len(normalized), index + len(name) + window)
        candidate = normalized[start:end].strip()
        # Cửa sổ phải THẬT SỰ chứa nhãn. Không kiểm điều này thì lần xuất hiện
        # đầu của "traffic" sẽ trả về đoạn quanh "traffic light" cho cả
        # "traffic sign" — dẫn chứng sai nhưng trông hợp lệ.
        if name in candidate:
            prefix = "…" if start > 0 else ""
            suffix = "…" if end < len(normalized) else ""
            return f"{prefix}{candidate}{suffix}"
        start_at = index + 1


def _cells(line: str) -> list[str]:
    """Các ô của một dòng bảng Markdown."""
    if not line.startswith("|"):
        return []
    return [cell.strip() for cell in line.strip("|").split("|")]


def _numeric(text: str) -> bool:
    """Ô có phải một con số (kể cả `0,85` hay `1.00`)."""
    return bool(re.fullmatch(r"\d+(?:[.,]\d+)?", text.strip()))


def _description_cell(line: str, point: str) -> str | None:
    """Ô mô tả, nếu dòng là **dòng riêng của đúng điểm này**.

    Hai dạng dòng riêng có thật trong nguồn, phải nhận cả hai:

    * ``| 15 | Mí trên, một phần tư ngoài | 0,21 |`` — 3 ô, ô cuối là tỉ lệ;
    * ``| 1 | Nose | Chóp mũi. Mặt nghiêng vẫn là chóp mũi… |`` — 3 ô, ô cuối là
      mô tả chữ (guideline pose17 không có cột tỉ lệ).

    Dạng bị loại là **bảng tra cứu** ``| 1 | Nose | 10 | R Wrist |``: 4 ô, ghép
    hai cặp (điểm, tên) của hai nửa bảng. Dòng này đúng là có điểm 1 nhưng không
    mô tả vị trí giải phẫu, nên không được dùng làm dẫn chứng.
    """
    cells = _cells(line)
    if len(cells) != 3:
        return None
    left = cells[0]
    if not re.fullmatch(rf"0*{re.escape(point)}", left):
        return None
    last = cells[2]
    if _numeric(last):
        return f"| {left} | {cells[1]} | {last} |"
    # Ô cuối là chữ: nhận khi nó thật sự là một câu mô tả, không phải một mẩu tên
    # (`| 6 | R Shoulder | …` hợp lệ; `| 1 | Nose | 10 |` đã bị loại vì 4 ô).
    if len(last.split()) >= 3 and len(last) >= 15:
        return f"| {left} | {cells[1]} | {last} |"
    return None


def _range_clauses(line: str) -> list[tuple[int, int]]:
    """Mọi khoảng số trên một dòng, tách theo dấu ngăn mệnh đề.

    Tách theo mệnh đề là cần thiết: dòng
    ``longmaytrai | 0 … 4 | 5 | 4 | 0-1-2-3-4, hở hai đầu`` chứa cả `0 … 4` lẫn
    `0-1-2-3-4`; gộp cả dòng rồi bắt khoảng sẽ ra kết quả sai.
    """
    clauses = re.split(r"[.,;()|·]|\s{2,}", line)
    found: list[tuple[int, int]] = []
    for clause in clauses:
        match = re.search(r"(\d+)\s*[–—−-]\s*(\d+)", clause)
        if match:
            found.append((int(match.group(1)), int(match.group(2))))
    return found


def _skeleton_evidence(text: str, point: str) -> str | None:
    """Dẫn chứng cho một điểm skeleton.

    Chọn theo **thứ hạng**, không theo dòng khớp đầu tiên. Bản đầu lấy dòng khớp
    đầu và đã sai theo hai cách, cả hai đều im lặng:

    * pose17: bảng tra cứu ``| 1 | Nose | 10 | R Wrist |`` đứng trước bảng mô tả,
      nên **cả 17 điểm** nhận dẫn chứng khô không nói gì về vị trí;
    * face50: câu ``ID chạy liên tục 0–49 …`` khớp *mọi* điểm 0–49 và đứng trước
      bảng nhóm, nên 13 điểm môi/mày nhận dẫn chứng chung thay vì nhóm của mình.

    Thứ hạng: (1) dòng riêng của đúng điểm; (2) dòng khai khoảng **hẹp nhất** chứa
    điểm. Khoảng trải từ 25 điểm trở lên bị loại vì nó khớp gần cả bài nên không
    chứng minh được gì.
    """
    number = int(point)
    dedicated: list[str] = []
    ranged: list[tuple[int, str]] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cell = _description_cell(line, point)
        if cell:
            dedicated.append(cell)
        for low, high in _range_clauses(line):
            if low <= number <= high and (high - low) < 25:
                ranged.append((high - low, line))

    if dedicated:
        return dedicated[0]
    if ranged:
        span, line = min(ranged, key=lambda item: item[0])
        low, high = next(
            (lo, hi) for lo, hi in _range_clauses(line) if lo <= number <= hi
        )
        return f"{line}  (điểm {point} nằm trong khoảng {low}–{high} của nhóm này)"
    return None


def build_profile(task: str, source: str) -> tuple[Profile, list[str]]:
    """Dựng profile cho một bài. Trả về (profile, ghi chú)."""
    notes: list[str] = []
    source_path = SOURCES_DIR / source
    if not source_path.is_file():
        raise SystemExit(f"không thấy tài liệu nguồn: {source_path}")

    labels, task_shape = taxonomy_index()
    text = read_source_text(Profile(task=task, source=source, source_sha256=""))
    if text is None:
        notes.append(
            f"chưa có bản trích xuất {generated_markdown(source).relative_to(ROOT).as_posix()}; "
            "chạy `python tools/sync_all.py` trước"
        )
        text = ""

    shape = task_shape.get(task, "")
    entries: list[ProfileEntry] = []
    reasons: list[str] = []

    for (task_key, name), info in labels.items():
        if task_key != task:
            continue
        if task in ("pose17", "face50"):
            evidence = _skeleton_evidence(text, name) if text else None
        else:
            # Nhãn chữ: tìm trên bản đã gộp khoảng trắng để không trượt vì bảng
            # PDF bị vắt dòng.
            evidence = None
            if text:
                for raw in text.splitlines():
                    if name in raw:
                        evidence = raw.strip()
                        break
                if evidence is None:
                    evidence = _wrapped_label_evidence(text, name)
        if evidence is None:
            reasons.append(
                f"`{name}`: không tìm thấy dẫn chứng trong nguồn — giữ chờ, cần người xác nhận"
            )
            continue
        entries.append(
            ProfileEntry(
                document_label=name,
                model_label=name,
                shape=shape,
                support="full",
                evidence=evidence,
            )
        )

    profile = Profile(
        task=task,
        source=source,
        source_sha256=sha256_file(source_path),
        status="pending",
        entries=entries,
        reasons=reasons,
        generated_by="tools/guidelines.py generate (offline)",
    )

    # Chỉ nâng lên `applied` khi qua sạch kiểm tra. Nhờ vậy `status` là kết luận
    # của bộ kiểm, không phải lời hứa của người sinh.
    problems = validate_profile(profile, source_text=text)
    if not problems and not reasons and entries:
        profile.status = "applied"
        profile.reasons = []
    else:
        profile.status = "pending"
        profile.reasons = [*reasons, *problems]
    return profile, notes


def cmd_generate() -> int:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for task, source in TASK_SOURCES.items():
        profile, notes = build_profile(task, source)
        path = PROFILES_DIR / f"{task}.yaml"
        path.write_text(dump_profile(profile), encoding="utf-8")
        written += 1
        state = "applied" if profile.status == "applied" else "pending"
        print(
            f"  {path.relative_to(ROOT).as_posix()}: {len(profile.entries)} mục, {state}"
        )
        for note in notes:
            print(f"      chú ý: {note}")
        for reason in profile.reasons[:4]:
            print(f"      chờ: {reason}")

    skipped = [t for t in ("drivable", "lane", "lidar3d") if t not in TASK_SOURCES]
    if skipped:
        print(
            f"\nBỏ qua {', '.join(skipped)}: không có tài liệu nguồn chuẩn khai label "
            "của chúng (drivable/lane chỉ xấp xỉ từ COCO), nên không có dẫn chứng thật "
            "để trích."
        )
    print(f"\nĐã sinh {written} profile trong {PROFILES_DIR.relative_to(ROOT).as_posix()}/")
    return 0


def cmd_check() -> int:
    applied, problems = check_all()
    if problems:
        print("LỖI profile:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"OK: {applied} profile đang có hiệu lực, không có lỗi.")
    return 0


def cmd_status() -> int:
    profiles = load_profiles()
    if not profiles:
        print("Chưa có profile nào. Chạy: python tools/guidelines.py generate")
        return 0
    for name, profile in sorted(profiles.items()):
        mark = "CÓ HIỆU LỰC" if profile.status == "applied" else "CHỜ"
        print(f"{name:<10} {mark:<12} {len(profile.entries)} mục  <- {profile.source}")
        for reason in profile.reasons[:3]:
            print(f"           {reason}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate", help="sinh lại profile từ tài liệu nguồn (offline)")
    sub.add_parser("check", help="kiểm profile, thoát khác 0 nếu lỗi")
    sub.add_parser("status", help="profile nào có hiệu lực")
    args = parser.parse_args(argv)

    if args.command == "generate":
        return cmd_generate()
    if args.command == "check":
        return cmd_check()
    return cmd_status()


if __name__ == "__main__":
    sys.exit(main())
