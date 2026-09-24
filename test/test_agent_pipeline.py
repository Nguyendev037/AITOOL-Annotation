"""Test cho cầu nối landmark -> guideline -> payload CVAT.

Ba thứ được khoá ở đây, vì sai một trong ba là ghi annotation sai mà không ai biết:

1. Payload skeleton phải đúng định dạng CVAT 2.74 đã kiểm chứng thật
   (xem `work/verify_skeleton_write.py`).
2. Luật ngưỡng cả-skeleton của guideline mục 4.2 phải đánh Outside **cả nhóm**,
   không phải từng điểm rời rạc.
3. Điểm Outside vẫn phải được gửi kèm `outside: true` — bỏ điểm đi sẽ làm schema
   thiếu node.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from browser_agent.geometry import FACE_POINTS, POSE17_POINTS  # noqa: E402
from browser_agent.vision.landmarks import (  # noqa: E402
    OCCLUDED,
    OUTSIDE,
    VISIBLE,
    MappingReport,
    MappedPoint,
)
from browser_agent.vision.pipeline import (  # noqa: E402
    SkeletonLabels,
    VisionPayloadError,
    apply_skeleton_thresholds,
    expected_sublabels,
    landmarks_from_payload,
    map_payload,
    observations_from_payload,
    points_to_skeleton_shape,
)


def _point(point_id: int, name: str, group: str, state: str = VISIBLE) -> MappedPoint:
    return MappedPoint(
        point_id=point_id, name=name, group=group, x=0.5, y=0.5, state=state
    )


def _face_report(states: dict[str, str]) -> MappingReport:
    """Report 50 điểm mặt, trạng thái lấy theo nhóm từ ``states``."""
    points = [
        _point(spec.point_id, spec.name, spec.group, states.get(spec.group, VISIBLE))
        for spec in FACE_POINTS
    ]
    return MappingReport(points=points, warnings=[])


# --------------------------------------------------------------------------- #
# luật ngưỡng cả-skeleton (guideline 4.2)
# --------------------------------------------------------------------------- #
def test_below_threshold_turns_the_whole_group_outside():
    """mattrai dưới 4/8 -> Outside CẢ skeleton, không phải chỉ điểm lẻ."""
    report = _face_report({})
    # 3 điểm mắt trái mất hẳn -> còn 5/8. Vẫn trên ngưỡng.
    for point in report.points:
        if point.group == "mattrai" and point.point_id in (19, 20, 21):
            point.state = OUTSIDE
    warnings = apply_skeleton_thresholds(report)
    assert not [w for w in warnings if w.startswith("mattrai")]

    # mất thêm 2 điểm nữa -> 3/8, dưới ngưỡng 4 -> cả nhóm Outside.
    for point in report.points:
        if point.group == "mattrai" and point.point_id in (17, 18):
            point.state = OUTSIDE
    report2 = _face_report({})
    for point in report2.points:
        if point.group == "mattrai" and point.point_id in (17, 18, 19, 20, 21):
            point.state = OUTSIDE
    warnings2 = apply_skeleton_thresholds(report2)
    members = [p for p in report2.points if p.group == "mattrai"]
    assert all(p.state == OUTSIDE for p in members), "cả mattrai phải Outside"
    assert any("mattrai" in w for w in warnings2)


def test_moitrong_threshold_is_four_of_eight():
    report = _face_report({})
    for point in report.points:
        if point.group == "moitrong" and point.point_id >= 46:
            point.state = OUTSIDE  # còn 4/8 -> đúng ngưỡng, phải giữ
    apply_skeleton_thresholds(report)
    assert any(p.state != OUTSIDE for p in report.points if p.group == "moitrong")


def test_longmay_threshold_is_three_of_five():
    report = _face_report({})
    for point in report.points:
        if point.group == "longmaytrai" and point.point_id >= 2:
            point.state = OUTSIDE  # còn 2/5 -> dưới ngưỡng 3
    apply_skeleton_thresholds(report)
    members = [p for p in report.points if p.group == "longmaytrai"]
    assert all(p.state == OUTSIDE for p in members)


def test_skeleton_with_no_visible_point_adds_no_noise_warning():
    """Nhóm đã Outside sẵn từ đầu thì không cần thêm cảnh báo trùng."""
    report = _face_report({"mattrai": OUTSIDE})
    warnings = apply_skeleton_thresholds(report)
    assert not [w for w in warnings if w.startswith("mattrai")]


def test_occluded_points_still_count_towards_the_threshold():
    """Guideline: 'điểm không thấy đánh Occluded' — tức Occluded vẫn được tính là còn căn cứ."""
    report = _face_report({})
    for point in report.points:
        if point.group == "mattrai" and point.point_id in (14, 15, 16, 17):
            point.state = OCCLUDED
        elif point.group == "mattrai":
            point.state = OUTSIDE
    apply_skeleton_thresholds(report)
    members = [p for p in report.points if p.group == "mattrai"]
    assert sum(1 for p in members if p.state == OCCLUDED) == 4
    assert sum(1 for p in members if p.state == OUTSIDE) == 4


# --------------------------------------------------------------------------- #
# payload shape CVAT
# --------------------------------------------------------------------------- #
def test_skeleton_shape_matches_verified_cvat_format():
    labels = SkeletonLabels(label_id=437, sublabels={name: 438 + i for i, name in enumerate(str(n) for n in range(1, 18))})
    points = [_point(spec.point_id, spec.name, spec.group) for spec in POSE17_POINTS]
    shape = points_to_skeleton_shape(points, labels, frame=3)

    assert shape["type"] == "skeleton"
    assert shape["label_id"] == 437
    assert shape["frame"] == 3
    # Shape cha của skeleton không mang toạ độ; toạ độ nằm ở element.
    assert shape["points"] == []
    assert len(shape["elements"]) == 17
    first = shape["elements"][0]
    assert set(first) >= {"label_id", "frame", "type", "points", "outside", "occluded"}
    assert first["type"] == "points"
    assert first["label_id"] == 438
    assert [e["label_id"] for e in shape["elements"]] == list(range(438, 455))


def test_outside_points_are_still_sent_with_the_outside_flag():
    labels = SkeletonLabels(label_id=1, sublabels={str(n): n for n in range(1, 18)})
    points = [_point(spec.point_id, spec.name, spec.group) for spec in POSE17_POINTS]
    points[0].state = OUTSIDE
    points[1].state = OCCLUDED
    shape = points_to_skeleton_shape(points, labels, frame=0)

    assert len(shape["elements"]) == 17, "không được bỏ điểm ngoài khung"
    assert shape["elements"][0]["outside"] is True
    assert shape["elements"][1]["occluded"] is True
    assert shape["elements"][2]["outside"] is False


def test_missing_sublabel_raises_instead_of_silently_writing_wrong_point():
    labels = SkeletonLabels(label_id=1, sublabels={"1": 10})
    points = [_point(spec.point_id, spec.name, spec.group) for spec in POSE17_POINTS]
    with pytest.raises(VisionPayloadError) as exc:
        points_to_skeleton_shape(points, labels, frame=0)
    assert "sublabel" in str(exc.value)


# --------------------------------------------------------------------------- #
# payload worker -> observation
# --------------------------------------------------------------------------- #
def test_worker_payload_is_rejected_when_it_reports_failure():
    with pytest.raises(VisionPayloadError) as exc:
        observations_from_payload({"ok": False, "error": "không thấy ảnh"})
    assert "không thấy ảnh" in str(exc.value)


def test_landmarks_from_payload_tolerates_missing_optional_fields():
    items = [{"index": 0, "x": 0.1, "y": 0.2}]
    result = landmarks_from_payload(items)
    assert result[0].x == 0.1
    assert result[0].visibility == 1.0
    assert result[0].z == 0.0


def test_map_payload_pose17_from_synthetic_worker_payload():
    """Payload tối thiểu đủ 29 điểm -> 17 điểm guideline, không điểm nào bịa."""
    pose = [{"index": i, "x": 0.5, "y": 0.5, "visibility": 0.9} for i in range(33)]
    payload = {"ok": True, "width": 100, "height": 50, "rotation": 0, "pose": pose, "face": []}
    report, warnings = map_payload(payload, task="pose17")
    assert len(report.points) == 17
    # Toạ độ đã nhân theo kích thước ảnh thật.
    assert max(p.x for p in report.points) == pytest.approx(50.0)


def test_map_payload_rejects_unknown_task():
    with pytest.raises(VisionPayloadError):
        map_payload({"ok": True, "pose": [], "face": []}, task="không-có-bài-này")


def test_expected_sublabels_are_numeric_strings_for_both_tasks():
    assert expected_sublabels("pose17") == {str(n) for n in range(1, 18)}
    assert expected_sublabels("face50") == {str(n) for n in range(50)}
    assert len(expected_sublabels("face50")) == 50
