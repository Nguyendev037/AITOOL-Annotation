"""Test cho profile guideline (`browser_agent/guideline_profiles.py` + `tools/guidelines.py`).

Vì sao phần lớn test ở đây dựng tình huống **sai**: một bộ kiểm profile luôn trả
về "hợp lệ" thì trông vẫn xanh mà vô dụng. Giá trị thật của nó là bắt được
`model_label` không có trong taxonomy, shape không khớp, `source_sha256` cũ, và
đặc biệt là **dẫn chứng bịa** — dẫn chứng không tồn tại trong tài liệu nguồn.

Bài học đã trả giá để có file này: `taxonomy_index` từng khoá theo tên label nên
`rider`/`car`/`bicycle` của bbox bị nhóm semantic ghi đè, và các điểm `1`..`17`
của pose17 bị face50 ghi đè. Kết quả: bbox mất 7/10 label, pose17 mất cả 17.
Test `test_taxonomy_index_khong_bi_ghi_de` khoá lại đúng lỗi đó.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import guidelines  # noqa: E402
from browser_agent import guideline_profiles as gp  # noqa: E402
from browser_agent.guideline_profiles import (  # noqa: E402
    Profile,
    ProfileEntry,
    validate_profile,
)


# --------------------------------------------------------------------------- #
# taxonomy_index — khoá theo (task, label)
# --------------------------------------------------------------------------- #
def test_taxonomy_index_khong_bi_ghi_de() -> None:
    """Tên label trùng giữa các nhóm KHÔNG được ghi đè nhau.

    `rider`, `car`, `truck`, `bicycle` có ở cả `objects` (bbox) và `semantic`;
    điểm `1`..`17` có ở cả `pose17` và `face50`.
    """
    labels, shapes = gp.taxonomy_index()
    assert ("bbox", "rider") in labels
    assert ("semantic", "rider") in labels
    assert labels[("bbox", "rider")]["group"] == "objects"
    assert labels[("semantic", "rider")]["group"] == "semantic"
    assert ("pose17", "1") in labels
    assert ("face50", "1") in labels
    assert shapes["pose17"] == "skeleton"
    assert shapes["face50"] == "skeleton"


def test_so_label_moi_bai_dung_nhu_taxonomy() -> None:
    labels, _ = gp.taxonomy_index()
    counts: dict[str, int] = {}
    for task, _name in labels:
        counts[task] = counts.get(task, 0) + 1
    assert counts["bbox"] == 10
    assert counts["pose17"] == 17
    assert counts["face50"] == 50
    assert counts["semantic"] == 19


# --------------------------------------------------------------------------- #
# Profile thật trong repo
# --------------------------------------------------------------------------- #
def test_profile_trong_repo_deu_qua_kiem() -> None:
    applied, problems = gp.check_all()
    assert problems == []
    assert applied == 4, "bbox/face50/pose17/semantic phải có hiệu lực"


def test_moi_profile_phu_het_label_cua_bai() -> None:
    """Profile phải khai đủ label của task, không được bỏ sót âm thầm."""
    labels, _ = gp.taxonomy_index()
    for name, profile in gp.load_profiles().items():
        expected = {label for (task, label) in labels if task == profile.task}
        got = {e.model_label for e in profile.entries}
        assert got == expected, f"{name}: thiếu {expected - got}"


def test_dan_chung_trong_profile_co_that_trong_nguon() -> None:
    """Luật đáng giá nhất: dẫn chứng phải là chữ thật của nguồn, không được bịa."""
    for name, profile in gp.load_profiles().items():
        text = gp.read_source_text(profile)
        assert text is not None, f"{name}: chưa có bản trích xuất"
        for entry in profile.entries:
            core = gp._evidence_core(entry.evidence)
            assert core in text or " ".join(core.split()) in " ".join(text.split()), (
                f"{name}/{entry.model_label}: dẫn chứng không có trong nguồn"
            )


def test_duong_dan_nguon_trong_profile_la_that() -> None:
    for profile in gp.load_profiles().values():
        assert (gp.SOURCES_DIR / profile.source).is_file()


# --------------------------------------------------------------------------- #
# Bộ kiểm phải BẮT được lỗi (dựng tình huống sai)
# --------------------------------------------------------------------------- #
def _good_profile() -> Profile:
    profile = gp.load_profiles()["bbox"]
    return Profile(
        task=profile.task,
        source=profile.source,
        source_sha256=profile.source_sha256,
        status="pending",
        entries=list(profile.entries),
        generated_by="test",
    )


def test_bat_model_label_khong_co_trong_taxonomy() -> None:
    profile = _good_profile()
    profile.entries[0] = ProfileEntry(
        document_label="x",
        model_label="khong-co-label-nay",
        shape="rectangle",
        support="full",
        evidence=profile.entries[0].evidence,
    )
    problems = validate_profile(profile, source_text=gp.read_source_text(profile))
    assert any("không có trong taxonomy.yaml" in p for p in problems)


def test_bat_shape_khong_khop() -> None:
    profile = _good_profile()
    profile.entries[0] = ProfileEntry(
        document_label=profile.entries[0].document_label,
        model_label=profile.entries[0].model_label,
        shape="polyline",  # bbox phải là rectangle
        support="full",
        evidence=profile.entries[0].evidence,
    )
    problems = validate_profile(profile, source_text=gp.read_source_text(profile))
    assert any("shape" in p for p in problems)


def test_bat_trung_anh_xa() -> None:
    profile = _good_profile()
    profile.entries.append(profile.entries[0])
    problems = validate_profile(profile, source_text=gp.read_source_text(profile))
    assert any("hai lần" in p for p in problems)


def test_bat_source_sha256_cu() -> None:
    profile = _good_profile()
    profile.source_sha256 = "0" * 64
    problems = validate_profile(profile, source_text=gp.read_source_text(profile))
    assert any("source_sha256" in p for p in problems)


def test_bat_dan_chung_bia() -> None:
    """Dẫn chứng không tồn tại trong nguồn phải bị bắt — đây là luật số 6."""
    profile = _good_profile()
    profile.entries[0] = ProfileEntry(
        document_label=profile.entries[0].document_label,
        model_label=profile.entries[0].model_label,
        shape=profile.entries[0].shape,
        support="full",
        evidence="câu này hoàn toàn bịa ra và không có trong tài liệu",
    )
    problems = validate_profile(profile, source_text=gp.read_source_text(profile))
    assert any("dẫn chứng không có" in p for p in problems)


def test_profile_applied_ma_con_loi_thi_bao() -> None:
    """Profile lỗi không được phép mang trạng thái có hiệu lực."""
    profile = _good_profile()
    profile.status = "applied"
    profile.entries[0] = ProfileEntry(
        document_label="x",
        model_label="khong-co-label-nay",
        shape="rectangle",
        support="full",
        evidence=profile.entries[0].evidence,
    )
    problems = validate_profile(profile, source_text=gp.read_source_text(profile))
    assert any("không được có hiệu lực" in p for p in problems)


def test_bat_task_khong_co_trong_taxonomy() -> None:
    profile = _good_profile()
    profile.task = "khong-co-bai-nay"
    problems = validate_profile(profile, source_text=gp.read_source_text(profile))
    assert any("không có trong taxonomy.yaml" in p for p in problems)


def test_source_khong_ton_tai_thi_bao() -> None:
    profile = _good_profile()
    profile.source = "khong-co-tai-lieu-nay.pdf"
    problems = validate_profile(profile, source_text=None)
    assert any("không thấy tài liệu nguồn" in p for p in problems)


# --------------------------------------------------------------------------- #
# Sinh profile
# --------------------------------------------------------------------------- #
def test_sinh_lai_profile_cho_ket_qua_giong_het() -> None:
    """Sinh phải tất định: chạy hai lần ra cùng nội dung, nếu không thì không kiểm được."""
    first = {
        task: guidelines.dump_profile(guidelines.build_profile(task, src)[0])
        for task, src in guidelines.TASK_SOURCES.items()
    }
    second = {
        task: guidelines.dump_profile(guidelines.build_profile(task, src)[0])
        for task, src in guidelines.TASK_SOURCES.items()
    }
    assert first == second


def test_profile_dang_trong_repo_khop_voi_ban_sinh_lai() -> None:
    """Profile trong repo phải là bản vừa sinh — lệch nghĩa là có người sửa tay."""
    for task, source in guidelines.TASK_SOURCES.items():
        expected = guidelines.dump_profile(guidelines.build_profile(task, source)[0])
        actual = (gp.PROFILES_DIR / f"{task}.yaml").read_text(encoding="utf-8")
        assert actual == expected, f"{task}.yaml không khớp bản sinh lại"


def test_sinh_profile_khong_goi_llm() -> None:
    """Sinh mặc định phải chạy offline: mọi thứ cần đều có trong nguồn + taxonomy."""
    import inspect

    source = inspect.getsource(guidelines)
    assert "openai" not in source.lower(), "đường sinh không được phụ thuộc LLM"


def test_status_khong_ghi_file(capsys: pytest.CaptureFixture[str]) -> None:
    before = {p: p.read_text(encoding="utf-8") for p in gp.PROFILES_DIR.glob("*.yaml")}
    assert guidelines.cmd_status() == 0
    after = {p: p.read_text(encoding="utf-8") for p in gp.PROFILES_DIR.glob("*.yaml")}
    assert before == after


def test_check_khong_ghi_file() -> None:
    before = {p: p.read_text(encoding="utf-8") for p in gp.PROFILES_DIR.glob("*.yaml")}
    guidelines.cmd_check()
    after = {p: p.read_text(encoding="utf-8") for p in gp.PROFILES_DIR.glob("*.yaml")}
    assert before == after


# --------------------------------------------------------------------------- #
# _evidence_core — bỏ dấu do người sinh thêm, giữ chữ của nguồn
# --------------------------------------------------------------------------- #
def test_evidence_core_bo_dau_cat_va_chu_thich() -> None:
    assert gp._evidence_core("…abc…") == "abc"
    assert gp._evidence_core("| moingoai | 30 – 41 | 12 |  (điểm 38 nằm trong khoảng)") == (
        "| moingoai | 30 – 41 | 12 |"
    )
    assert gp._evidence_core("| 1 | Nose |") == "| 1 | Nose |"


def test_face50_diem_38_duoc_dan_chung_theo_khoang_hep() -> None:
    """Điểm 38 không có dòng riêng, nhưng phải lấy đúng nhóm hẹp nhất chứa nó.

    Lỗi đã xảy ra: hàm chọn dẫn chứng lấy **dòng khớp đầu tiên**, nên câu
    ``ID chạy liên tục 0–49 …`` khớp mọi điểm 0–49 và che mất bảng nhóm. 13 điểm
    môi/mày nhận dẫn chứng chung thay vì nhóm của mình. Điểm 38 thuộc nhóm
    ``moingoai`` (30–41) nhưng dòng riêng của nó bị bản trích xuất làm mất, nên
    dẫn chứng phải là khoảng ``37 – 41`` của bảng mô tả môi dưới.
    """
    profile = gp.load_profiles()["face50"]
    entry = next(e for e in profile.entries if e.model_label == "38")
    assert "37 – 41" in entry.evidence
    assert "0–49" not in entry.evidence, "không được lấy câu khớp mọi điểm"
    assert "37 – 41" in entry.evidence  # dẫn chứng theo khoảng, ghi rõ trong ngoặc
    assert "khoảng" in entry.evidence


def test_dan_chung_rong_khong_bao_gio_duoc_dung() -> None:
    """Câu khớp gần cả bài (khoảng ≥25 điểm) không chứng minh được gì."""
    for name, profile in gp.load_profiles().items():
        for entry in profile.entries:
            assert "0–49" not in entry.evidence, f"{name}/{entry.model_label}"


def test_pose17_moi_diem_co_dan_chung_vi_tri_giai_phau() -> None:
    """pose17 phải lấy bảng mô tả, không lấy bảng tra cứu ``| 1 | Nose | 10 | R Wrist |``.

    Lỗi đã xảy ra: bảng tra cứu đứng trước nên **cả 17 điểm** nhận dẫn chứng khô
    không nói gì về vị trí. Nhận diện bảng tra cứu bằng **cấu trúc 4 ô** (ghép hai
    cặp điểm–tên), không bằng chữ "R Wrist": điểm 10 có tên nhãn đúng là "R Wrist"
    nên tìm theo chữ sẽ bắt oan chính dòng mô tả.
    """
    profile = gp.load_profiles()["pose17"]
    for entry in profile.entries:
        cells = gp_evidence_cells(entry.evidence)
        assert len(cells) == 3, (
            f"{entry.model_label}: phải là dòng mô tả 3 ô, đang {len(cells)} ô "
            f"(4 ô là bảng tra cứu): {entry.evidence!r}"
        )
        assert len(cells[2].split()) >= 3, (
            f"{entry.model_label}: ô cuối không phải câu mô tả: {cells[2]!r}"
        )


def gp_evidence_cells(evidence: str) -> list[str]:
    return [c.strip() for c in evidence.strip().strip("|").split("|")]
