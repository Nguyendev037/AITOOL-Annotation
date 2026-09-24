"""Test cho model registry (`models.yaml` + `tools/models.py`).

Vì sao các test này tồn tại: registry là thứ quyết định model nào chạy và model
nào bị gỡ khỏi CVAT. Một registry "trông đúng" nhưng không được kiểm sẽ khiến
model đã tắt vẫn được triển khai — hoặc model đang bật bị gỡ nhầm.

Phần đáng chú ý nhất là nhóm test về `sync-cvat --check`: bài học từ
`sync_all.py --check` là một lệnh "chỉ kiểm tra" vẫn có thể ghi file. Ở đây điều
đó được kiểm bằng chính việc so nội dung file trước/sau.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import models  # noqa: E402


def _write_registry(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(body, encoding="utf-8")
    return path


GOOD = """
version: 1
models:
  - id: a
    task: bbox
    annotations: rectangle
    backend: model-service
    function: smart-bbox
    enabled: true
    default: true
"""


# --------------------------------------------------------------------------- #
# Đọc + kiểm cấu trúc
# --------------------------------------------------------------------------- #
def test_registry_that_doc_duoc() -> None:
    entries = models.load_registry()
    assert {e.id for e in entries} >= {
        "bbox-yolo26m",
        "semantic-eomt",
        "drivable-eomt",
        "lane-classical",
        "pose17-mediapipe",
        "face50-mediapipe",
    }


def test_moi_task_dang_bat_co_dung_mot_mac_dinh() -> None:
    entries = models.load_registry()
    for task in {e.task for e in entries if e.enabled}:
        defaults = [e for e in entries if e.task == task and e.enabled and e.default]
        assert len(defaults) == 1, f"task {task} có {len(defaults)} mặc định"


def test_hai_mac_dinh_cung_task_bi_tu_choi(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path,
        GOOD
        + """
  - id: b
    task: bbox
    annotations: rectangle
    backend: model-service
    function: smart-drivable
    enabled: true
    default: true
""",
    )
    with pytest.raises(models.RegistryError, match="nhiều hơn một model"):
        models.load_registry(path)


def test_backend_la_khong_hop_le_bi_tu_choi(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path, GOOD.replace("backend: model-service", "backend: quantum")
    )
    with pytest.raises(models.RegistryError, match="backend"):
        models.load_registry(path)


def test_model_remote_thieu_function_bi_tu_choi(tmp_path: Path) -> None:
    path = _write_registry(tmp_path, GOOD.replace("    function: smart-bbox\n", ""))
    with pytest.raises(models.RegistryError, match="function"):
        models.load_registry(path)


def test_model_local_khong_duoc_khai_function(tmp_path: Path) -> None:
    """Model chạy tại chỗ mà khai function là mâu thuẫn: sẽ đi tìm function không có."""
    path = _write_registry(
        tmp_path, GOOD.replace("backend: model-service", "backend: local")
    )
    with pytest.raises(models.RegistryError, match="local"):
        models.load_registry(path)


def test_trung_id_bi_tu_choi(tmp_path: Path) -> None:
    path = _write_registry(tmp_path, GOOD + GOOD.split("models:\n")[1])
    with pytest.raises(models.RegistryError, match="trùng"):
        models.load_registry(path)


# --------------------------------------------------------------------------- #
# resolve_model — chỗ endpoint/browser-agent dùng để từ chối model đã tắt
# --------------------------------------------------------------------------- #
def test_resolve_tra_ve_mac_dinh_cua_task() -> None:
    entries = models.load_registry()
    assert models.resolve_model(entries, "bbox").id == "bbox-yolo26m"
    assert models.resolve_model(entries, "face50").id == "face50-mediapipe"


def test_model_da_tat_khong_bao_gio_duoc_resolve(tmp_path: Path) -> None:
    body = GOOD.replace("enabled: true", "enabled: false")
    path = _write_registry(tmp_path, body)
    entries = models.load_registry(path)
    with pytest.raises(models.RegistryError, match="không có model nào đang bật"):
        models.resolve_model(entries, "bbox")


def test_task_khong_ton_tai_thi_bao_ro() -> None:
    entries = models.load_registry()
    with pytest.raises(models.RegistryError, match="không có model"):
        models.resolve_model(entries, "khong-co-bai-nay")


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #
def test_check_registry_sach_tren_du_lieu_that() -> None:
    assert models.check_registry() == []


def test_check_bat_task_khong_co_trong_taxonomy(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path, GOOD.replace("task: bbox", "task: khong-co-trong-taxonomy")
    )
    problems = models.check_registry(models.load_registry(path))
    assert any("taxonomy.yaml" in p for p in problems)


def test_check_bat_function_khong_ton_tai(tmp_path: Path) -> None:
    path = _write_registry(tmp_path, GOOD.replace("smart-bbox", "smart-khong-co"))
    problems = models.check_registry(models.load_registry(path))
    assert any("không có nuclio function" in p for p in problems)


def test_function_specs_dung_ten_trong_metadata_khong_phai_ten_file() -> None:
    """Tên function (`smart-bbox`) khác tên file (`bbox.yaml`).

    Trộn hai thứ này là lỗi thật đã gặp: kiểm tra đi tìm `smart-bbox.yaml` và báo
    thiếu cả 4 function trong khi chúng vẫn nằm đó.
    """
    specs = models.function_specs()
    assert "smart-bbox" in specs
    assert specs["smart-bbox"].name == "bbox.yaml"


def test_check_bat_checkpoint_thieu(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path, GOOD + "    checkpoint: model-service/weights/khong-co.pt\n"
    )
    problems = models.check_registry(models.load_registry(path))
    assert any("checkpoint" in p for p in problems)


def test_checkpoint_dung_bien_moi_truong_khong_co_thi_bao_thieu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BROWSER_AGENT_MEDIAPIPE_MODEL_DIR", raising=False)
    path = _write_registry(
        tmp_path,
        GOOD
        + "    checkpoint: ${BROWSER_AGENT_MEDIAPIPE_MODEL_DIR}/x.task\n",
    )
    entry = models.load_registry(path)[0]
    assert entry.checkpoint is None, "biến môi trường thiếu phải cho checkpoint None"


# --------------------------------------------------------------------------- #
# sync-cvat: lên kế hoạch
# --------------------------------------------------------------------------- #
def test_plan_sync_trien_khai_model_dang_bat() -> None:
    entries = models.load_registry()
    actions, skipped = models.plan_sync(entries, present=set())
    deploying = {a.function for a in actions if a.kind == "deploy"}
    assert deploying == {"smart-bbox", "smart-semantic", "smart-drivable", "smart-lane"}
    assert all(a.kind == "deploy" for a in actions)


def test_plan_sync_bo_qua_model_local_va_noi_ro() -> None:
    entries = models.load_registry()
    _, skipped = models.plan_sync(entries, present=set())
    joined = " ".join(skipped)
    for local in ("pose17-mediapipe", "face50-mediapipe", "lidar-cuboid-fit"):
        assert local in joined
    assert all("local" in note for note in skipped)


def test_plan_sync_go_function_cua_model_da_tat(tmp_path: Path) -> None:
    """Model tắt thì function của nó phải bị gỡ khỏi trang Models của CVAT."""
    body = GOOD.replace(
        "    enabled: true\n    default: true\n", "    enabled: false\n"
    )
    entries = models.load_registry(_write_registry(tmp_path, body))
    actions, _ = models.plan_sync(entries, present={"smart-bbox"})
    assert [a.kind for a in actions] == ["delete"]
    assert actions[0].function == "smart-bbox"


def test_plan_sync_khong_go_khi_chua_doc_duoc_dashboard() -> None:
    """`present=None` nghĩa là chưa đọc được dashboard -> không được đoán mà gỡ."""
    entries = models.load_registry()
    actions, _ = models.plan_sync(entries, present=None)
    assert all(a.kind == "deploy" for a in actions)


def test_plan_sync_khong_dung_toi_function_khong_thuoc_du_an() -> None:
    """Function lạ trên dashboard (của người khác) không được đụng tới."""
    entries = models.load_registry()
    actions, _ = models.plan_sync(entries, present={"sam2-large-api", "foo"})
    assert all(a.function != "sam2-large-api" for a in actions)


# --------------------------------------------------------------------------- #
# sync-cvat --check: TUYỆT ĐỐI không ghi
# --------------------------------------------------------------------------- #
def test_sync_cvat_check_khong_ghi_gi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Đây là test quan trọng nhất của file: `--check` không được đổi một file nào.

    Kiểm bằng chính nội dung file, không tin vào việc hàm "trông có vẻ" chỉ đọc.
    """
    entries = models.load_registry()
    before = {
        path: path.read_text(encoding="utf-8")
        for path in [
            ROOT / "models.yaml",
            ROOT / "model-service" / "taxonomy.json",
            ROOT / "guideline" / "README.md",
        ]
    }
    monkeypatch.setattr(models, "_read_dashboard_functions", lambda: set())
    monkeypatch.setattr(
        models, "_apply_actions", lambda *a, **k: pytest.fail("--check đã gọi _apply_actions")
    )
    code = models._cmd_sync_cvat(entries, check=True)
    assert code == 0
    after = {path: path.read_text(encoding="utf-8") for path in before}
    assert before == after, "--check đã ghi file"


# --------------------------------------------------------------------------- #
# enable/disable: sửa file mà không phá chú thích
# --------------------------------------------------------------------------- #
def test_enable_disable_giu_nguyen_chu_thich(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`yaml.safe_dump` sẽ xoá sạch chú thích — phần đáng giá nhất của file."""
    target = _write_registry(tmp_path, "# chú thích quan trọng\n" + GOOD)
    monkeypatch.setattr(models, "REGISTRY_YAML", target)

    models.set_flag("a", "enabled", False)
    text = target.read_text(encoding="utf-8")
    assert "# chú thích quan trọng" in text, "chú thích bị mất"
    assert "enabled: false" in text

    models.set_flag("a", "enabled", True)
    assert "enabled: true" in target.read_text(encoding="utf-8")


def test_khong_dat_mac_dinh_cho_model_dang_tat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _write_registry(
        tmp_path, GOOD.replace("enabled: true", "enabled: false")
    )
    monkeypatch.setattr(models, "REGISTRY_YAML", target)
    with pytest.raises(models.RegistryError, match="đang tắt"):
        models.set_flag("a", "default", True)


def test_sua_model_khong_ton_tai_thi_bao_ro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _write_registry(tmp_path, GOOD)
    monkeypatch.setattr(models, "REGISTRY_YAML", target)
    with pytest.raises(models.RegistryError, match="không có model"):
        models.set_flag("khong-co", "enabled", False)
