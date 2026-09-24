"""Luật số của Week 2: đọc từ `rules/` và đối chiếu với tài liệu nguồn.

Vì sao module này tồn tại
------------------------
Trước đây ngưỡng cả-skeleton (guideline mục 4.2) nằm cứng trong
`vision/pipeline.py`. Hệ quả đã đo được bằng thí nghiệm
(`work/rule_autoupdate_probe.py`): sửa tài liệu nguồn rồi chạy `sync_all.py` thì
**bản trích xuất cập nhật, nhưng hành vi agent thì không** — rule mới nằm trong
markdown còn agent vẫn dùng số cũ.

Module này tách luật thành **dữ liệu** (`rules/week2-rules.json`) và thêm một bước
**đối chiếu bắt buộc** với câu chữ trong guideline sinh tự động. Nhờ vậy:

- Sửa ngưỡng là sửa JSON, không phải sửa Python.
- Nếu tài liệu đổi ngưỡng mà JSON chưa đổi, `check_rules` **báo lỗi ngay** thay vì
  để agent chạy sai âm thầm.

Vì sao không đọc thẳng markdown để điều khiển hành vi: câu chữ guideline là văn xuôi
và bảng biểu tự do; tự suy ra hành vi từ đó sẽ sai lặng lẽ. Cách ở đây giữ **một**
nguồn cho hành vi, đồng thời ép phát hiện lệch.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES = ROOT / "rules" / "week2-rules.json"

#: Câu khai ngưỡng trong bảng guideline, ví dụ "Từ 4/8 điểm trở lên".
_THRESHOLD = re.compile(r"Từ\s*(\d+)\s*/\s*(\d+)\s*điểm\s*trở\s*lên")

#: Tài liệu nguồn chính thức của bài mặt. Đây mới là thứ BTC phát hành, nên là mốc
#: đối chiếu đúng. Đối chiếu với bản Markdown sinh tự động là sai: bản đó do LLM
#: viết lại và có thể không được sinh ra chút nào (xem `FACE_GUIDELINE`).
FACE_SOURCE = ROOT / "guildlline" / "Week2_Guideline_Face_Landmark_VF50_HocVien_v1.3.docx"

#: Bản Markdown sinh tự động — chỉ dùng làm phương án dự phòng khi không có docx.
FACE_GUIDELINE = (
    ROOT / "guideline" / "generated" / "week2-guideline-face-landmark-vf50-hocvien-v1-3.md"
)


class RulesError(RuntimeError):
    """File luật thiếu/hỏng hoặc lệch với tài liệu nguồn."""


def load_rules(path: Path | None = None) -> dict:
    target = path or DEFAULT_RULES
    if not target.is_file():
        raise RulesError(f"không thấy file luật {target}")
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RulesError(f"{target.name} không phải JSON hợp lệ: {exc}") from exc


def skeleton_min_points(path: Path | None = None) -> dict[str, tuple[int, int]]:
    """``{nhóm: (tối thiểu, tổng)}`` cho bài mặt.

    Trả về tuple để chỗ dùng không phụ thuộc hình dạng JSON, và để đổi cấu trúc file
    luật không phải sửa caller.
    """
    data = load_rules(path)
    try:
        raw = data["face50"]["skeleton_min_points"]
    except KeyError as exc:
        raise RulesError("file luật thiếu mục face50.skeleton_min_points") from exc
    result: dict[str, tuple[int, int]] = {}
    for group, spec in raw.items():
        try:
            result[group] = (int(spec["minimum"]), int(spec["total"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise RulesError(f"luật của nhóm {group!r} sai định dạng: {spec!r}") from exc
    return result


def _names_in_cell(cell: str) -> list[str]:
    """Tách tên nhóm trong một ô: ``"mattrai, matphai"`` -> ``["mattrai", "matphai"]``."""
    return [
        part.strip()
        for part in cell.split(",")
        if part.strip() and not part.strip().startswith("-")
    ]


def thresholds_from_docx(path: Path) -> dict[str, tuple[int, int]]:
    """Đọc ngưỡng thẳng từ **bảng trong tài liệu nguồn** `.docx`.

    Vì sao đọc docx chứ không đọc bản Markdown sinh ra: bản Markdown do một lần gọi
    LLM viết lại, nên (a) cần `DEEPSEEK_API_KEY`, (b) có thể không tồn tại, (c) nội
    dung có thể bị diễn giải lại. Mốc đối chiếu phải là thứ BTC phát hành.
    """
    if not path.is_file():
        raise RulesError(f"không thấy tài liệu nguồn {path}")
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - thiếu thư viện là lỗi môi trường
        raise RulesError("cần python-docx để đọc tài liệu nguồn: pip install python-docx") from exc

    found: dict[str, tuple[int, int]] = {}
    for table in Document(str(path)).tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if not cells:
                continue
            match = _THRESHOLD.search(cells[1] if len(cells) > 1 else cells[0])
            if not match:
                continue
            value = (int(match.group(1)), int(match.group(2)))
            for name in _names_in_cell(cells[0]):
                found[name] = value
    return found


def thresholds_in_guideline(path: Path | None = None) -> dict[str, tuple[int, int]]:
    """Ngưỡng theo tài liệu nguồn (docx); nếu không có thì đọc bản Markdown.

    Chỉ lấy từ bảng để không bắt nhầm con số nằm trong văn xuôi. Một dòng có thể khai
    nhiều nhóm: ``| mattrai, matphai | Từ 4/8 ... |``.
    """
    if path is not None:
        target = Path(path)
        if target.suffix.lower() == ".docx":
            return thresholds_from_docx(target)
    else:
        target = FACE_SOURCE
        if target.is_file():
            return thresholds_from_docx(target)
        target = FACE_GUIDELINE

    if not target.is_file():
        raise RulesError(
            f"không thấy tài liệu nguồn {FACE_SOURCE.relative_to(ROOT)} "
            f"lẫn bản sinh {target.relative_to(ROOT)}"
        )
    found: dict[str, tuple[int, int]] = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        match = _THRESHOLD.search(stripped)
        if not match:
            continue
        minimum, total = int(match.group(1)), int(match.group(2))
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        for name in _names_in_cell(cells[0]):
            if name:
                found[name] = (minimum, total)
    return found


def compare(path: Path | None = None, guideline: Path | None = None) -> list[str]:
    """So luật đang dùng với guideline. Trả về danh sách lệch (rỗng = khớp)."""
    configured = skeleton_min_points(path)
    documented = thresholds_in_guideline(guideline)
    problems: list[str] = []

    for group, value in sorted(documented.items()):
        if group not in configured:
            problems.append(
                f"guideline khai ngưỡng cho {group!r} ({value[0]}/{value[1]}) "
                f"nhưng rules/week2-rules.json không có nhóm này"
            )
        elif configured[group] != value:
            problems.append(
                f"{group}: guideline ghi {value[0]}/{value[1]} nhưng luật đang dùng "
                f"{configured[group][0]}/{configured[group][1]}"
            )

    for group in sorted(set(configured) - set(documented)):
        problems.append(
            f"{group}: có trong luật nhưng guideline không khai ngưỡng "
            f"(kiểm tra lại tài liệu hoặc xoá khỏi file luật)"
        )
    return problems
