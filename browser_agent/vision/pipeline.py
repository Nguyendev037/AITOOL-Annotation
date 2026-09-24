"""Nối landmark thô -> điểm theo guideline -> payload shape cho CVAT.

Ba tầng, cố ý tách rời:

1. ``worker_landmarks.py`` (venv lõi, có mediapipe) → landmark **thô**, chỉ toạ độ.
2. ``browser_agent.vision.landmarks`` (repo này) → điểm theo **lược đồ guideline**,
   kèm trạng thái Visible/Occluded/Outside và cảnh báo.
3. module này → **payload shape** đúng định dạng CVAT đã kiểm chứng.

Nhờ vậy không có chỗ nào thứ hai quyết định point ID hay trạng thái, và tầng 3
không cần biết gì về MediaPipe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..geometry import (
    FACE_POINTS,
    FACE_SKELETONS,
    POSE17_LABEL_CANDIDATES,
    POSE17_POINTS,
    POSE17_SKELETON,
)
from .landmarks import (
    OUTSIDE,
    MappingReport,
    MappedPoint,
    map_face50,
    map_pose17,
)
from .mediapipe_pose import FaceObservation, PoseObservation, RawLandmark

def skeleton_thresholds(path: Path | None = None) -> tuple[tuple[str, int, int], ...]:
    """Luật ngưỡng cả-skeleton, đọc từ `rules/week2-rules.json`.

    Trước đây hằng số này nằm cứng trong module, nên khi tài liệu nguồn đổi ngưỡng
    thì bản trích xuất cập nhật mà **hành vi agent thì không** (đã đo bằng
    `work/rule_autoupdate_probe.py`). Nay luật là dữ liệu; đổi ngưỡng là sửa JSON.
    """
    from .rules import skeleton_min_points

    return tuple(
        (group, minimum, total)
        for group, (minimum, total) in skeleton_min_points(path).items()
    )


#: Luật đang dùng, đọc lúc import để giữ tương thích với chỗ cũ.
SKELETON_THRESHOLDS: tuple[tuple[str, int, int], ...] = skeleton_thresholds()


class VisionPayloadError(RuntimeError):
    """Payload landmark thô không dùng được."""


# --------------------------------------------------------------------------- #
# landmark thô -> observation
# --------------------------------------------------------------------------- #
def landmarks_from_payload(items: list[dict] | None) -> list[RawLandmark]:
    """Đổi danh sách dict của worker thành ``RawLandmark``.

    Chấp nhận thiếu khoá: worker có thể chỉ trả ``x``/``y`` cho FaceMesh.
    """
    result: list[RawLandmark] = []
    for position, item in enumerate(items or []):
        try:
            result.append(
                RawLandmark(
                    index=int(item.get("index", position)),
                    x=float(item.get("x", 0.0)),
                    y=float(item.get("y", 0.0)),
                    z=float(item.get("z", 0.0)),
                    visibility=float(item.get("visibility", 1.0)),
                    presence=float(item.get("presence", 1.0)),
                )
            )
        except (TypeError, ValueError) as exc:
            raise VisionPayloadError(f"landmark #{position} sai định dạng: {item!r}") from exc
    return result


def observations_from_payload(payload: dict[str, Any]) -> tuple[PoseObservation, FaceObservation]:
    """Tách payload của worker thành hai observation."""
    if not payload.get("ok", False):
        raise VisionPayloadError(f"worker báo lỗi: {payload.get('error') or 'không rõ'}")
    rotation = int(payload.get("rotation") or 0)
    return (
        PoseObservation(landmarks=landmarks_from_payload(payload.get("pose")), rotation_applied=rotation),
        FaceObservation(landmarks=landmarks_from_payload(payload.get("face")), rotation_applied=rotation),
    )


# --------------------------------------------------------------------------- #
# luật ngưỡng cả-skeleton (guideline mục 4.2)
# --------------------------------------------------------------------------- #
def apply_skeleton_thresholds(report: MappingReport) -> list[str]:
    """Đánh Outside cả skeleton khi số điểm thấy được dưới ngưỡng.

    Guideline mục 4.2: "Áp dụng khi cả một bộ phận bị che, thay vì xét từng điểm".
    Ví dụ mắt: từ 4/8 điểm trở lên thì đặt đủ contour và điểm không thấy đánh
    Occluded; **dưới 4/8 thì Outside cả skeleton**.

    Hàm sửa ``report`` tại chỗ và trả về danh sách cảnh báo đã thêm, để người dùng
    biết vì sao một nhóm biến mất khỏi kết quả.
    """
    warnings: list[str] = []
    seen = {point.state for point in report.points}
    # Skeleton chưa có trạng thái gì (model không thấy điểm nào) thì đã Outside sẵn.
    if seen <= {OUTSIDE}:
        return warnings

    for group, minimum, total in SKELETON_THRESHOLDS:
        members = [point for point in report.points if point.group == group]
        if not members:
            continue
        visible = sum(1 for point in members if point.state != OUTSIDE)
        if visible >= minimum:
            continue
        # Nhóm vốn đã Outside sạch (model không thấy gì) thì không cần đổi gì và
        # cũng không nên thêm cảnh báo — cảnh báo đó chỉ là nhiễu.
        if visible == 0:
            continue
        for point in members:
            point.state = OUTSIDE
            point.note = f"cả {group} bị đánh Outside (chỉ {visible}/{total} điểm còn căn cứ)"
        warnings.append(
            f"{group}: chỉ {visible}/{total} điểm còn căn cứ (< {minimum}) -> đánh Outside cả skeleton"
        )
    return warnings


def map_payload(
    payload: dict[str, Any], *, task: str
) -> tuple[MappingReport, list[str]]:
    """Payload worker -> ``MappingReport`` cho ``task`` ∈ {``pose17``, ``face50``}.

    Trả ``(report, warnings)``. ``warnings`` gộp cả cảnh báo của tầng map và của
    luật ngưỡng.
    """
    pose, face = observations_from_payload(payload)
    width = float(payload.get("width") or 1.0)
    height = float(payload.get("height") or 1.0)

    key = task.strip().lower()
    if key in {"pose17", "pose", "body"}:
        report = map_pose17(pose, wid=width, hei=height)
    elif key in {"face50", "face", "vf50"}:
        report = map_face50(face, wid=width, hei=height)
        report.warnings.extend(apply_skeleton_thresholds(report))
    else:
        raise VisionPayloadError(f"không biết task {task!r}; có: pose17, face50")

    if not payload.get("pose") and key.startswith("pose"):
        report.warnings.append("worker không trả landmark pose nào")
    return report, list(report.warnings)


# --------------------------------------------------------------------------- #
# điểm đã map -> payload shape của CVAT
# --------------------------------------------------------------------------- #
@dataclass
class SkeletonLabels:
    """Id label/subLabel thật đọc từ CVAT cho một skeleton."""

    label_id: int
    sublabels: dict[str, int] = field(default_factory=dict)

    def sublabel_id(self, name: str) -> int:
        try:
            return self.sublabels[name]
        except KeyError as exc:
            raise VisionPayloadError(
                f"skeleton không có sublabel {name!r}; đang có: "
                f"{', '.join(sorted(self.sublabels, key=_numeric)) or '(không có)'}"
            ) from exc


def _numeric(value: str) -> tuple[int, str]:
    return (int(value), "") if value.isdigit() else (10**6, value)


def points_to_skeleton_shape(
    points: list[MappedPoint],
    labels: SkeletonLabels,
    *,
    frame: int,
    source: str = "auto",
    group: int = 0,
) -> dict[str, Any]:
    """Dựng payload skeleton đúng định dạng CVAT 2.74 đã kiểm chứng.

    Định dạng này đã chạy thật trên CVAT localhost (`work/verify_skeleton_write.py`):
    shape cha type ``skeleton`` với ``points: []``, mỗi sublabel là một element type
    ``points`` mang ``label_id`` của sublabel đó.

    Điểm ``Outside`` **vẫn được gửi** kèm ``outside: true``: guideline yêu cầu schema
    của skeleton phải đủ điểm, và CVAT lưu trạng thái ngoài khung bằng cờ này chứ
    không phải bằng cách bỏ điểm.
    """
    elements = []
    for point in points:
        elements.append(
            {
                "label_id": labels.sublabel_id(point.name),
                "frame": frame,
                "type": "points",
                "points": [round(point.x, 4), round(point.y, 4)],
                "outside": point.outside,
                "occluded": point.occluded,
                "attributes": [],
            }
        )
    return {
        "label_id": labels.label_id,
        "frame": frame,
        "type": "skeleton",
        "points": [],
        "outside": False,
        "occluded": False,
        "attributes": [],
        "source": source,
        "group": group,
        "elements": elements,
    }


def face_group_shapes(
    report: MappingReport,
    labels_by_group: dict[str, SkeletonLabels],
    *,
    frame: int,
    source: str = "auto",
) -> list[dict[str, Any]]:
    """Bài mặt: mỗi nhóm guideline là một skeleton riêng.

    Guideline VF-50 định nghĩa 7 skeleton (longmaytrai, longmayphai, songmui,
    mattrai, matphai, moingoai, moitrong). Nếu CVAT cấu hình cả bài mặt thành MỘT
    skeleton thì dùng ``points_to_skeleton_shape`` với toàn bộ 50 điểm.
    """
    by_group = report.by_group()
    shapes: list[dict[str, Any]] = []
    for spec in FACE_SKELETONS:
        labels = labels_by_group.get(spec.name)
        if labels is None:
            continue
        members = by_group.get(spec.name) or []
        if not members:
            continue
        shapes.append(
            points_to_skeleton_shape(members, labels, frame=frame, source=source, group=len(shapes))
        )
    return shapes


def expected_sublabels(task: str) -> set[str]:
    """Tập sublabel mà schema phải có, để soát trước khi ghi."""
    key = task.strip().lower()
    if key in {"pose17", "pose", "body"}:
        return {point.name for point in POSE17_POINTS}
    if key in {"face50", "face", "vf50"}:
        return {point.name for point in FACE_POINTS}
    raise VisionPayloadError(f"không biết task {task!r}")


__all__ = [
    "SKELETON_THRESHOLDS",
    "SkeletonLabels",
    "VisionPayloadError",
    "apply_skeleton_thresholds",
    "expected_sublabels",
    "face_group_shapes",
    "landmarks_from_payload",
    "map_payload",
    "observations_from_payload",
    "points_to_skeleton_shape",
    "POSE17_LABEL_CANDIDATES",
]
