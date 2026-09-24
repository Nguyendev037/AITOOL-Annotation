"""Test cho luật số Week 2 (`browser_agent/vision/rules.py`).

Vì sao test này quan trọng hơn vẻ ngoài của nó: tính năng "agent tự nhận diện rule"
chỉ có giá trị nếu **phát hiện được lúc luật lệch tài liệu**. Một bộ đối chiếu luôn
trả về "khớp" thì trông vẫn xanh mà vô dụng. Nên phần lớn test ở đây dựng tình huống
lệch giả và đòi hỏi bộ đối chiếu **phải báo**.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from browser_agent.vision import rules  # noqa: E402
from browser_agent.vision.pipeline import skeleton_thresholds  # noqa: E402

GUIDELINE = rules.FACE_GUIDELINE


def test_luat_that_khop_guideline_that() -> None:
    """File luật trong repo phải khớp tài liệu sinh tự động — đây là hợp đồng chính."""
    assert rules.compare() == []


def test_doc_duoc_tat_ca_sau_nhom_mat() -> None:
    configured = rules.skeleton_min_points()
    assert set(configured) == {
        "mattrai", "matphai", "longmaytrai", "longmayphai", "moingoai", "moitrong"
    }
    assert configured["moingoai"] == (6, 12)
    assert configured["longmaytrai"] == (3, 5)


def test_guideline_that_co_nguong_giong_luat() -> None:
    """Bộ đọc phải thật sự đọc ra số, không phải trả rỗng rồi 'khớp' may mắn."""
    documented = rules.thresholds_in_guideline()
    assert len(documented) == 6, f"chỉ đọc được {documented}"
    assert documented["mattrai"] == (4, 8)


def test_doi_chieu_thang_tai_lieu_nguon_docx() -> None:
    """Mốc đối chiếu phải là docx nguồn BTC phát hành, không phải bản Markdown.

    Đây là bài học từ thí nghiệm thật: bản Markdown do một lần gọi LLM viết lại và
    cần `DEEPSEEK_API_KEY`; khi thiếu key thì `sync_guidelines.py` thoát ngay, nên
    nếu chỉ đối chiếu với bản sinh ra thì bộ kiểm tra sẽ im lặng vô ích.
    """
    assert rules.FACE_SOURCE.is_file(), "thiếu tài liệu nguồn trong guildlline/"
    assert rules.FACE_SOURCE.suffix == ".docx"
    documented = rules.thresholds_from_docx(rules.FACE_SOURCE)
    assert documented["mattrai"] == (4, 8)
    assert documented["moingoai"] == (6, 12)
    # Mặc định (không truyền đường dẫn) phải đi qua docx.
    assert rules.thresholds_in_guideline() == documented


def test_bao_loi_ro_khi_thieu_tai_lieu_nguon(tmp_path: Path) -> None:
    with pytest.raises(rules.RulesError):
        rules.thresholds_from_docx(tmp_path / "khong-ton-tai.docx")


def test_bang_trong_docx_khong_bat_nham_van_xuoi(tmp_path: Path) -> None:
    """Chỉ ô trong bảng mới tính; câu văn chứa '4/8' không được thành luật."""
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("Phải có ít nhất 9/9 điểm mới tính — câu này là văn xuôi.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "mattrai, matphai"
    table.rows[0].cells[1].text = "Từ 4/8 điểm trở lên"
    target = tmp_path / "nguon.docx"
    document.save(str(target))

    documented = rules.thresholds_from_docx(target)
    assert documented == {"mattrai": (4, 8), "matphai": (4, 8)}


def test_khong_bat_nham_so_trong_van_xuoi(tmp_path: Path) -> None:
    """Chỉ đọc dòng bảng: con số nằm trong câu văn không được tính là luật."""
    fake = tmp_path / "g.md"
    fake.write_text(
        "# Tiêu đề\n\n"
        "Phải có ít nhất 4/8 điểm thì mới tính, theo mục 4.2.\n\n"
        "| Nhóm | Ngưỡng |\n|---|---|\n"
        "| mattrai, matphai | Từ 4/8 điểm trở lên |\n",
        encoding="utf-8",
    )
    documented = rules.thresholds_in_guideline(fake)
    assert documented == {"mattrai": (4, 8), "matphai": (4, 8)}


def test_phat_hien_guideline_doi_nguong(tmp_path: Path) -> None:
    """Tài liệu đổi 4/8 -> 5/8 mà luật chưa đổi thì PHẢI báo lệch."""
    fake = tmp_path / "g.md"
    fake.write_text(
        "| Nhóm | Ngưỡng |\n|---|---|\n"
        "| mattrai, matphai | Từ 5/8 điểm trở lên |\n"
        "| longmaytrai, longmayphai | Từ 3/5 điểm trở lên |\n"
        "| moingoai | Từ 6/12 điểm trở lên |\n"
        "| moitrong | Từ 4/8 điểm trở lên |\n",
        encoding="utf-8",
    )
    problems = rules.compare(guideline=fake)
    assert any("mattrai" in p and "5/8" in p for p in problems), problems


def test_phat_hien_nhom_moi_trong_guideline(tmp_path: Path) -> None:
    """Guideline thêm nhóm mới mà luật không có thì phải báo, không được bỏ qua."""
    fake = tmp_path / "g.md"
    fake.write_text(
        "| Nhóm | Ngưỡng |\n|---|---|\n"
        "| mattrai, matphai | Từ 4/8 điểm trở lên |\n"
        "| longmaytrai, longmayphai | Từ 3/5 điểm trở lên |\n"
        "| moingoai | Từ 6/12 điểm trở lên |\n"
        "| moitrong | Từ 4/8 điểm trở lên |\n"
        "| canhmuigia | Từ 2/4 điểm trở lên |\n",
        encoding="utf-8",
    )
    problems = rules.compare(guideline=fake)
    assert any("canhmuigia" in p for p in problems), problems


def test_luat_thieu_nhom_guideline_co_thi_bao(tmp_path: Path) -> None:
    """Ngược lại: luật khai nhóm guideline không có ngưỡng thì cũng là lệch."""
    short = tmp_path / "r.json"
    short.write_text(
        json.dumps({"version": 1, "face50": {"skeleton_min_points": {"mattrai": {"minimum": 4, "total": 8}}}}),
        encoding="utf-8",
    )
    problems = rules.compare(short)
    assert any("moingoai" in p for p in problems), problems
    assert any("matphai" in p for p in problems), problems


def test_json_hong_thi_bao_loi_ro(tmp_path: Path) -> None:
    bad = tmp_path / "r.json"
    bad.write_text("{ khong phai json", encoding="utf-8")
    with pytest.raises(rules.RulesError):
        rules.load_rules(bad)


def test_json_thieu_muc_thi_bao_loi_ro(tmp_path: Path) -> None:
    bad = tmp_path / "r.json"
    bad.write_text(json.dumps({"version": 1}), encoding="utf-8")
    with pytest.raises(rules.RulesError):
        rules.skeleton_min_points(bad)


def test_sai_dinh_dang_nguong_thi_bao_loi_ro(tmp_path: Path) -> None:
    bad = tmp_path / "r.json"
    bad.write_text(
        json.dumps({"version": 1, "face50": {"skeleton_min_points": {"mattrai": {"minimum": "bốn"}}}}),
        encoding="utf-8",
    )
    with pytest.raises(rules.RulesError):
        rules.skeleton_min_points(bad)


def test_pipeline_doc_luat_tu_du_lieu_khong_phai_hang_so(tmp_path: Path) -> None:
    """Điểm mấu chốt của cả tính năng: đổi file luật -> ngưỡng agent đổi theo.

    Nếu ai đó dán lại hằng số cứng vào pipeline, test này đổ.
    """
    fake = tmp_path / "r.json"
    fake.write_text(
        json.dumps(
            {
                "version": 2,
                "face50": {
                    "skeleton_min_points": {
                        "mattrai": {"minimum": 7, "total": 8},
                        "moingoai": {"minimum": 2, "total": 12},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    thresholds = dict((g, (m, t)) for g, m, t in skeleton_thresholds(fake))
    assert thresholds == {"mattrai": (7, 8), "moingoai": (2, 12)}
    # Và mặc định của repo vẫn là con số của guideline.
    assert dict((g, (m, t)) for g, m, t in skeleton_thresholds())["mattrai"] == (4, 8)


def test_hang_so_module_khop_file_luat() -> None:
    """SKELETON_THRESHOLDS (dùng ở chỗ cũ) phải chính là luật từ file."""
    from browser_agent.vision.pipeline import SKELETON_THRESHOLDS

    expected = tuple(
        (group, minimum, total)
        for group, (minimum, total) in rules.skeleton_min_points().items()
    )
    assert SKELETON_THRESHOLDS == expected
