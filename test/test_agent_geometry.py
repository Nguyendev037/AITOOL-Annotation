"""Test cho lược đồ điểm và tầng map landmark.

Chạy: python -m pytest test/test_agent_geometry.py -v
Không cần mediapipe, không cần ảnh, không cần mạng: chỉ kiểm tra hợp đồng với
guideline, tức những thứ mà sai một chút là hỏng cả bài annotation.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from browser_agent.geometry import (  # noqa: E402
    FACE_POINTS,
    FACE_POINT_COUNT,
    FACE_SKELETONS,
    MP_EYE_ANATOMICAL,
    MP_EYE_RING,
    MP_INNER_LIP_LOWER,
    MP_INNER_LIP_UPPER,
    MP_INNER_MOUTH,
    MP_NOSE_BRIDGE,
    MP_OUTER_LIP_LOWER,
    MP_OUTER_LIP_UPPER,
    MP_OUTER_MOUTH,
    POSE17_ANATOMICAL_PAIRS,
    POSE17_EDGES,
    POSE17_POINT_BY_ID,
    POSE17_POINT_COUNT,
    POSE17_POINTS,
    POSE17_SIDE_PAIRS,
    face_edges,
    face_label_names,
)
from browser_agent.vision.landmarks import (  # noqa: E402
    OCCLUDED,
    OUTSIDE,
    VISIBLE,
    _arc_ratios,
    assign_face_sides,
    classify_state,
    face_side_swap_needed,
    map_face50,
    map_pose17,
    resolve_frame_side_indices,
)
from browser_agent.vision.mediapipe_pose import (  # noqa: E402
    FaceObservation,
    PoseObservation,
    RawLandmark,
)


# --------------------------------------------------------------------------- #
# lược đồ tĩnh
# --------------------------------------------------------------------------- #
def test_pose17_has_17_points_numbered_1_to_17():
    assert POSE17_POINT_COUNT == 17
    assert sorted(POSE17_POINT_BY_ID) == list(range(1, 18))
    # Sublabel gửi lên CVAT phải là chuỗi số, không dùng tên L_*/R_*.
    for point in POSE17_POINT_BY_ID.values():
        assert point.name == str(point.point_id)


def test_pose17_edges_match_guideline_topology():
    """Guideline mục 5.3 liệt kê đúng 18 cạnh; thừa/thiếu đều là lỗi schema."""
    assert len(POSE17_EDGES) == 18
    expected_head = {(1, 2), (1, 3), (2, 4), (3, 5), (4, 6), (5, 7)}
    assert expected_head.issubset(set(POSE17_EDGES))
    # Mỗi tay và mỗi chân phải liền mạch: 6-8-10, 7-9-11, 12-14-16, 13-15-17.
    for chain in ((6, 8, 10), (7, 9, 11), (12, 14, 16), (13, 15, 17)):
        for left, right in zip(chain, chain[1:]):
            assert (left, right) in POSE17_EDGES


def test_face_has_50_points_and_7_skeletons():
    assert FACE_POINT_COUNT == 50
    assert sorted(p.point_id for p in FACE_POINTS) == list(range(50))
    assert len(FACE_SKELETONS) == 7
    assert face_label_names() == (
        "longmaytrai",
        "longmayphai",
        "songmui",
        "mattrai",
        "matphai",
        "moingoai",
        "moitrong",
    )


def test_face_skeleton_point_ids_match_guideline_table():
    """Guideline mục 2.2: mattrai dùng 14-21 chứ KHÔNG phải 0-7."""
    spans = {spec.name: spec.point_ids for spec in FACE_SKELETONS}
    assert spans["longmaytrai"] == (0, 1, 2, 3, 4)
    assert spans["longmayphai"] == (5, 6, 7, 8, 9)
    assert spans["songmui"] == (10, 11, 12, 13)
    assert spans["mattrai"] == tuple(range(14, 22))
    assert spans["matphai"] == tuple(range(22, 30))
    assert spans["moingoai"] == tuple(range(30, 42))
    assert spans["moitrong"] == tuple(range(42, 50))
    # 50 node và 47 cạnh: 5 contour hở mất 4 cạnh so với khép kín.
    total_edges = sum(len(face_edges(spec)) for spec in FACE_SKELETONS)
    assert total_edges == 47


def test_face_mouth_and_nose_indices_are_facemesh_and_not_eye_indices():
    """Lỗi thật đã từng có: môi lấy nhầm index mắt (39/40/46/47/48)."""
    eye_indices = {i for group in MP_EYE_ANATOMICAL for i in group}
    mouth = set(MP_OUTER_MOUTH) | set(MP_INNER_MOUTH)
    assert not (mouth & eye_indices), f"môi trùng index mắt: {sorted(mouth & eye_indices)}"
    assert len(set(MP_OUTER_MOUTH)) == 12
    assert len(set(MP_INNER_MOUTH)) == 8
    assert len(set(MP_NOSE_BRIDGE)) == 4
    # 13 là chân sống mũi, KHÔNG phải chóp mũi (chóp mũi là index 4/1).
    assert 4 not in MP_NOSE_BRIDGE and 1 not in MP_NOSE_BRIDGE


def test_pose17_side_pairs_are_symmetric():
    rights = {r for r, _ in POSE17_SIDE_PAIRS}
    lefts = {l for _, l in POSE17_SIDE_PAIRS}
    assert rights == {2, 4, 6, 8, 10, 12, 14, 16}
    assert lefts == {3, 5, 7, 9, 11, 13, 15, 17}


# --------------------------------------------------------------------------- #
# trạng thái điểm
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("x", "y", "visibility", "expected"),
    [
        (-0.1, 0.5, 1.0, OUTSIDE),      # ngoài khung bên trái
        (1.5, 0.5, 1.0, OUTSIDE),       # ngoài khung bên phải
        (0.5, 0.5, 1.0, VISIBLE),       # thấy rõ
        (0.5, 0.5, 0.2, OCCLUDED),      # bị che nhưng còn căn cứ
        (0.5, 0.5, 0.01, OUTSIDE),      # model không thấy
    ],
)
def test_classify_state(x, y, visibility, expected):
    state, _ = classify_state(x, y, visibility=visibility, min_visibility=0.35)
    assert state == expected


def test_classify_state_flags_mediapipe_corner_dump_as_outside():
    """Guideline mô tả 'chùm điểm ở góc trên-trái'; đó là Outside, không phải Visible."""
    state, note = classify_state(0.01, 0.01, visibility=0.1, min_visibility=0.35)
    assert state == OUTSIDE
    assert "góc trên-trái" in note


def test_outside_beats_visibility_when_point_leaves_frame():
    state, _ = classify_state(1.04, 0.5, visibility=0.9, min_visibility=0.35)
    assert state == OUTSIDE


# --------------------------------------------------------------------------- #
# trái/phải theo khung hình
# --------------------------------------------------------------------------- #
def _face_landmarks(**overrides: tuple[float, float]) -> list[RawLandmark]:
    """478 landmark giả, nhưng có hình học mắt/môi THẬT theo mesh MediaPipe.

    Fixture phải dựng đủ **vòng 20 điểm** cho mỗi môi, vì `assign_face_sides` chọn
    12 điểm môi ngoài (và 8 điểm môi trong) từ vòng đó theo tỉ lệ cung. Bản trước
    chỉ dựng đúng 12/8 index cũ nên không còn kiểm được gì sau khi đổi cách chọn.
    """
    landmarks = [RawLandmark(i, 0.5, 0.5) for i in range(478)]

    def put(index: int, x: float, y: float) -> None:
        landmarks[index] = RawLandmark(index, x, y)

    # --- mắt: VÒNG ĐẦY ĐỦ 16 ĐỈNH, đúng như MediaPipe thật.
    # Fixture phải có đủ 16 đỉnh vì `assign_face_sides` CHỌN 8 điểm mí từ vòng này
    # theo hình học; nếu chỉ dựng 8 điểm thì việc chọn không có gì để chọn.
    # Mỗi vòng: khoé ngoài, 7 đỉnh mí dưới, khoé trong, 7 đỉnh mí trên.
    def eye_ring(outer: float, inner: float, indices: tuple[int, ...]) -> None:
        """Vòng mắt; ``outer``/``inner`` là x của hai khoé."""
        left_x, right_x = (outer, inner) if outer < inner else (inner, outer)
        for offset, index in enumerate(indices):
            if offset == 0:      # khoé ngoài (trái nhất)
                put(index, left_x, 0.400)
            elif offset == 8:    # khoé trong (phải nhất)
                put(index, right_x, 0.400)
            elif offset < 8:     # 7 đỉnh mí DƯỚI, võng xuống
                frac = offset / 8
                put(index, left_x + (right_x - left_x) * frac, 0.400 + 0.018 * (1 - abs(2 * frac - 1)))
            else:                # 7 đỉnh mí TRÊN, vồng lên
                frac = (16 - offset) / 8
                put(index, left_x + (right_x - left_x) * frac, 0.400 - 0.018 * (1 - abs(2 * frac - 1)))

    eye_ring(0.632, 0.568, MP_EYE_RING[0])   # MP right eye: bên PHẢI ảnh
    eye_ring(0.368, 0.432, MP_EYE_RING[1])   # MP left eye: bên TRÁI ảnh

    # --- lông mày: bờ trên hơi cong, đuôi ngoài thấp hơn ---
    puts = {
        46: (0.648, 0.372), 53: (0.624, 0.362), 52: (0.600, 0.358),
        65: (0.576, 0.362), 55: (0.552, 0.366),
        285: (0.448, 0.366), 295: (0.424, 0.362), 282: (0.400, 0.358),
        283: (0.376, 0.362), 276: (0.352, 0.372),
    }
    for index, (x, y) in puts.items():
        put(index, x, y)

    # --- môi: hai VÒNG 20 ĐIỂM theo đúng kết nối của MediaPipe ---------------
    # Vòng ngoài và vòng trong đều được dựng thành "thấu kính": nửa trên là một
    # đường, nửa dưới là một đường, hai khoé là hai đầu. Nhờ vậy tỉ lệ cung có
    # nghĩa và việc chọn 12/8 điểm kiểm được bằng số.
    def lip_ring_upper(upper: tuple[int, ...], mid: float, half: float) -> None:
        for offset, index in enumerate(upper):
            frac = offset / (len(upper) - 1)
            put(index, mid - half + 2 * half * frac, 0.600 - 0.050 * math.sin(math.pi * frac))

    def lip_ring_lower(lower: tuple[int, ...], mid: float, half: float) -> None:
        for offset, index in enumerate(lower):
            frac = offset / (len(lower) - 1)
            put(index, mid + half - 2 * half * frac, 0.600 + 0.050 * math.sin(math.pi * frac))

    lip_ring_upper(MP_OUTER_LIP_UPPER, 0.500, 0.080)
    lip_ring_lower(MP_OUTER_LIP_LOWER, 0.500, 0.080)
    lip_ring_upper(MP_INNER_LIP_UPPER, 0.500, 0.060)
    lip_ring_lower(MP_INNER_LIP_LOWER, 0.500, 0.060)

    # --- sống mũi: chạy dọc trục giữa, đủ dài để chọn 4 điểm chia đều ---
    for index, y in ((168, 0.330), (6, 0.350), (197, 0.370), (51, 0.400), (44, 0.430)):
        put(index, 0.500, y)

    for index, (x, y) in overrides.items():
        put(index, x, y)
    return landmarks


def test_face_sides_do_not_swap_when_orientation_is_normal():
    landmarks = _face_landmarks()
    swap, reason = face_side_swap_needed(landmarks)
    assert swap is False
    assert reason == ""


def test_face_sides_swap_when_anatomical_right_eye_is_on_image_left():
    """Mặt quay 180° hoặc ảnh lật: phải gán lại theo khung hình, không theo giải phẫu."""
    landmarks = [RawLandmark(i, 0.5, 0.5) for i in range(478)]
    for offset, index in enumerate(MP_EYE_ANATOMICAL[0]):
        landmarks[index] = RawLandmark(index, 0.30 + offset * 0.001, 0.40)
    for offset, index in enumerate(MP_EYE_ANATOMICAL[1]):
        landmarks[index] = RawLandmark(index, 0.70 - offset * 0.001, 0.40)

    swap, reason = face_side_swap_needed(landmarks)
    assert swap is True
    assert "đổi chỗ" in reason


def test_assign_face_sides_puts_lowest_x_eye_into_mattrai():
    landmarks = _face_landmarks()
    mapping, _ = assign_face_sides(landmarks)
    left_x = sum(landmarks[mapping[pid]].x for pid in range(14, 22)) / 8
    right_x = sum(landmarks[mapping[pid]].x for pid in range(22, 30)) / 8
    assert left_x < right_x, "mattrai phải nằm bên trái matphai trên khung hình"


def test_assign_face_sides_covers_all_50_points():
    landmarks = _face_landmarks()
    mapping, _ = assign_face_sides(landmarks)
    assert sorted(mapping) == list(range(50))
    # Mọi point ID phải trỏ tới một index có thật.
    assert all(0 <= index < len(landmarks) for index in mapping.values())
    # 12 điểm môi ngoài phải là 12 ĐỈNH KHÁC NHAU. Bản cũ để 41 trùng index với
    # một điểm môi trên, tức vẽ hai điểm chồng lên nhau — guideline không cho phép.
    outer = [mapping[pid] for pid in range(30, 42)]
    assert len(set(outer)) == 12, f"12 điểm môi ngoài phải khác nhau, đang có {len(set(outer))}"
    inner = [mapping[pid] for pid in range(42, 50)]
    assert len(set(inner)) == 8, f"8 điểm môi trong phải khác nhau, đang có {len(set(inner))}"


def test_brow_points_increase_in_x_from_0_to_9():
    """Guideline mục 5.2: "toạ độ x của các điểm 0 đến 9 tăng dần".

    Đây là mục checklist mà bản cũ HỎNG trên cả 5 frame thật của job 2214: nhóm
    longmaytrai bị sắp giảm dần nên x đi xuống ở 4 chặng đầu. Fixture dưới đây có
    x của 10 điểm tăng dần, nên nếu code sắp ngược thì test này đổ.
    """
    landmarks = _face_landmarks()
    mapping, _ = assign_face_sides(landmarks)
    xs = [landmarks[mapping[pid]].x for pid in range(10)]
    inversions = [
        (pid, xs[pid], xs[pid + 1]) for pid in range(9) if xs[pid + 1] < xs[pid]
    ]
    assert not inversions, f"x của điểm 0..9 phải tăng dần, hỏng ở: {inversions}"
    # Điểm 0 là trái nhất khung, điểm 9 là phải nhất.
    assert xs[0] == min(xs)
    assert xs[9] == max(xs)


def test_brow_points_keep_two_separate_groups():
    """Sắp lại thứ tự không được trộn hai bên mày vào nhau.

    Nếu ai đó "sửa" bằng cách sắp cả 10 điểm theo x mà quên tách nhóm, mày trái và
    mày phải sẽ xen kẽ -> hỏng topology dù mục 5.2 vẫn xanh.
    """
    landmarks = _face_landmarks()
    mapping, _ = assign_face_sides(landmarks)
    left_xs = [landmarks[mapping[pid]].x for pid in range(0, 5)]
    right_xs = [landmarks[mapping[pid]].x for pid in range(5, 10)]
    assert max(left_xs) < min(right_xs), "mày trái phải nằm hoàn toàn bên trái mày phải"


# --------------------------------------------------------------------------- #
# contour mắt: chống bắt chéo (guideline mục 3.3)
# --------------------------------------------------------------------------- #
def _contour_points(landmarks, mapping, base):
    return [landmarks[mapping[base + offset]] for offset in range(8)]


def test_eye_contour_starts_leftmost_and_ends_at_rightmost():
    """Guideline 3.3: điểm đầu 14/22 là trái nhất, điểm 18/26 là phải nhất."""
    landmarks = _face_landmarks()
    mapping, _ = assign_face_sides(landmarks)
    for base, start, end in ((14, 14, 18), (22, 22, 26)):
        points = _contour_points(landmarks, mapping, base)
        xs = [p.x for p in points]
        assert mapping[start] == points[0].index
        assert mapping[end] == points[4].index
        assert xs[0] == min(xs), "điểm đầu contour phải trái nhất"
        assert xs[4] == max(xs), "điểm khoé còn lại phải phải nhất"


def test_eye_contour_is_a_hairpin_not_an_x():
    """Không được bắt chéo: 3 mí trên đi trái->phải, 3 mí dưới đi phải->trái.

    Đây là bất biến mà cách sắp xếp thuần theo x vi phạm: nó trộn mí trên với mí
    dưới và tạo contour hình chữ X — đúng thứ guideline cấm.
    """
    landmarks = _face_landmarks()
    mapping, _ = assign_face_sides(landmarks)
    for base in (14, 22):
        points = _contour_points(landmarks, mapping, base)
        upper = points[1:4]
        lower = points[5:8]
        # mí trên chạy từ trái sang phải
        assert [p.x for p in upper] == sorted(p.x for p in upper)
        # mí dưới chạy từ phải về trái
        assert [p.x for p in lower] == sorted((p.x for p in lower), reverse=True)
        # và mọi điểm mí trên phải cao hơn (y nhỏ hơn) mọi điểm mí dưới
        assert max(p.y for p in upper) < min(p.y for p in lower)
        # đối chiếu từng cặp như guideline nêu: 15-21, 16-20, 17-19
        for top, bottom in zip(upper, reversed(lower)):
            assert top.y < bottom.y, f"mí trên {top.index} không cao hơn mí dưới {bottom.index}"


def test_eye_contour_keeps_the_same_eight_mediapipe_indices():
    """8 điểm chọn ra phải thuộc ĐÚNG vòng mắt của nó, và phải phân biệt được.

    Fixture đặt mắt PHẢI giải phẫu (``MP_EYE_RING[0]``) bên phải ảnh, nên nó phải
    vào ``matphai`` (22-29); mắt trái giải phẫu vào ``mattrai`` (14-21).
    """
    landmarks = _face_landmarks()
    mapping, _ = assign_face_sides(landmarks)
    for base, ring in ((22, MP_EYE_RING[0]), (14, MP_EYE_RING[1])):
        chosen = {mapping[base + offset] for offset in range(8)}
        assert chosen <= set(ring), "8 điểm phải nằm trong vòng mắt của chính nó"
        assert len(chosen) == 8
        # Hai khoé bắt buộc phải có mặt: chúng là điểm đầu và điểm thứ 5.
        assert mapping[base] in set(ring) and mapping[base + 4] in set(ring)


def test_eye_contour_is_rotation_invariant():
    """Xoay ảnh 30°: contour vẫn là hairpin, vì phe mí tính bằng dấu có hướng."""
    landmarks = _face_landmarks()
    angle = math.radians(30)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    rotated = []
    for p in landmarks:
        x, y = p.x - 0.5, p.y - 0.5
        rotated.append(RawLandmark(p.index, 0.5 + x * cos_a - y * sin_a, 0.5 + x * sin_a + y * cos_a))
    mapping, _ = assign_face_sides(rotated)
    for base in (14, 22):
        points = _contour_points(rotated, mapping, base)
        xs = [p.x for p in points]
        assert xs[0] == min(xs)
        assert xs[4] == max(xs)
        upper, lower = points[1:4], points[5:8]
        assert [p.x for p in upper] == sorted(p.x for p in upper)
        assert [p.x for p in lower] == sorted((p.x for p in lower), reverse=True)


def test_mouth_contours_start_at_left_corner_and_keep_ring_order():
    """Guideline 3.4: điểm 30 và 42 là khoé miệng trái; 36 và 46 là khoé phải.

    Thứ tự vòng kiểm bằng CUNG trên vòng thật của MediaPipe, không bằng toạ độ x:
    với môi gần nằm ngang, x của nửa môi dưới không đơn điệu dù thứ tự vòng đúng.
    """
    landmarks = _face_landmarks()
    mapping, _ = assign_face_sides(landmarks)
    for base, span, corner_right, left_idx, right_idx, upper_chain, lower_chain in (
        (30, 12, 36, 61, 291, MP_OUTER_LIP_UPPER, MP_OUTER_LIP_LOWER),
        (42, 8, 46, 78, 308, MP_INNER_LIP_UPPER, MP_INNER_LIP_LOWER),
    ):
        sequence = [mapping[base + offset] for offset in range(span)]
        assert mapping[base] == left_idx, f"điểm {base} phải là khoé trái MediaPipe"
        assert mapping[corner_right] == right_idx, f"điểm {corner_right} phải là khoé phải"
        assert len(set(sequence)) == span, "các điểm trong một môi phải khác nhau"

        # Mỗi nửa vòng phải được đọc theo ĐÚNG chiều cung của MediaPipe.
        upper_ids = [mapping[pid] for pid in range(base + 1, corner_right)]
        upper_arc = _arc_ratios(landmarks, upper_chain)
        assert [upper_arc[i] for i in upper_ids] == sorted(upper_arc[i] for i in upper_ids)

        # Nửa vòng dưới chạy từ khoé phải về khoé trái, nên cung GIẢM dần.
        lower_ids = [mapping[pid] for pid in range(corner_right + 1, base + span)]
        lower_arc = _arc_ratios(landmarks, lower_chain)
        ratios = [lower_arc[i] for i in lower_ids]
        assert ratios == sorted(ratios, reverse=True)


def test_mouth_lower_lip_points_spread_over_the_whole_lip():
    """Lỗi thật reviewer nêu: "miệng chưa khớp ... nối bị sai rất nhiều".

    Đo trên frame thật job 2214, bản cũ chọn 12 điểm môi ngoài bằng cách cắt 12
    phần tử đầu của vòng 20 điểm rồi quay theo x. Hệ quả: cả 5 điểm môi dưới
    (37..41) rơi vào index {267..291} — tức chỉ quanh khoé phải — và nửa môi dưới
    bên trái không có điểm nào. Test này khoá lại: các điểm môi dưới phải trải
    trên phần lớn chiều ngang của môi.
    """
    landmarks = _face_landmarks()
    mapping, _ = assign_face_sides(landmarks)
    outer_ring = set(MP_OUTER_LIP_UPPER) | set(MP_OUTER_LIP_LOWER)
    lower = [mapping[pid] for pid in (37, 38, 39, 40, 41)]
    assert set(lower).issubset(outer_ring), "điểm môi dưới phải thuộc vòng môi ngoài"

    left_x = landmarks[mapping[30]].x
    right_x = landmarks[mapping[36]].x
    span = right_x - left_x
    assert span > 0
    covered = (max(landmarks[i].x for i in lower) - min(landmarks[i].x for i in lower)) / span
    assert covered > 0.45, f"5 điểm môi dưới chỉ trải {covered:.0%} chiều ngang môi"

    # Điểm 41 gần khoé PHẢI (36) hơn, điểm 37 gần khoé TRÁI (30) hơn — đúng chiều
    # vòng: 30 -> môi trên -> 36 -> môi dưới -> về 30. Bản cũ để cả 5 điểm dồn ở
    # khoé phải nên tỉ lệ này sai hoàn toàn.
    assert abs(landmarks[mapping[41]].x - right_x) < abs(landmarks[mapping[37]].x - right_x)
    assert abs(landmarks[mapping[37]].x - left_x) < abs(landmarks[mapping[41]].x - left_x)

    # Nửa môi dưới phải có mặt ở cả hai phía của trục giữa môi.
    middle = (left_x + right_x) / 2
    assert min(landmarks[i].x for i in lower) < middle < max(landmarks[i].x for i in lower)


def test_nose_bridge_spans_the_nose_instead_of_stopping_halfway():
    """Lỗi thật reviewer nêu: "khương mũi quá ngắn so với thực tế".

    Bản cũ dùng thẳng (168, 6, 197, 195): trên frame thật job 2214 bộ này dừng ở
    y=349 trong khi nasion ở y=324 và chóp mũi ở y=377 — chỉ dài 27/53px. Test này
    đòi 4 điểm trải trên phần lớn chiều dài sống mũi, và 3 đoạn phải tương đối đều.
    """
    landmarks = _face_landmarks()
    mapping, _ = assign_face_sides(landmarks)
    ids = [mapping[pid] for pid in (10, 11, 12, 13)]
    assert len(set(ids)) == 4, "4 điểm sống mũi phải là 4 đỉnh khác nhau"

    ys = [landmarks[i].y for i in ids]
    assert ys == sorted(ys) or ys == sorted(ys, reverse=True), "sống mũi phải đi một chiều"
    # Chuỗi sống mũi chạy từ 168 xuống 44; điểm 13 phải chạm gần chóp.
    assert ids[-1] in (44, 45, 1), f"điểm 13 phải ở gần chóp mũi, đang là {ids[-1]}"

    full = abs(landmarks[44].y - landmarks[168].y)
    covered = abs(ys[-1] - ys[0]) / full
    assert covered > 0.8, f"4 điểm chỉ trải {covered:.0%} chiều dài sống mũi"

    segments = [abs(b - a) for a, b in zip(ys, ys[1:])]
    assert min(segments) > 0
    assert max(segments) / min(segments) < 1.6, f"3 đoạn sống mũi lệch nhau: {segments}"


def _pose_landmarks(
    *, shoulder_right_x: float, shoulder_left_x: float, visibility: float = 0.9
) -> list[RawLandmark]:
    """33 landmark giả. Các cặp KHÁC được đặt lệch x để không rơi vào trường hợp
    "hai bên trùng trục ngang" — ở đây chỉ muốn đo hành vi của cặp vai.

    ``shoulder_right_x`` là x của MediaPipe index 12 (vai GIẢI PHẪU phải),
    ``shoulder_left_x`` là x của index 11 (vai GIẢI PHẪU trái).
    """
    landmarks = [RawLandmark(i, 0.5, 0.5, visibility=visibility) for i in range(33)]
    # Mỗi cặp còn lại: index lẻ ở 0.55, index chẵn ở 0.45 (lệch nhau, không mơ hồ).
    for point_id, (odd, even) in POSE17_ANATOMICAL_PAIRS.items():
        if point_id == 6:      # cặp vai do tham số quyết định, đặt sau
            continue
        landmarks[odd] = RawLandmark(odd, 0.55, 0.50, visibility=visibility)
        landmarks[even] = RawLandmark(even, 0.45, 0.50, visibility=visibility)
    landmarks[12] = RawLandmark(12, shoulder_right_x, 0.30, visibility=visibility)
    landmarks[11] = RawLandmark(11, shoulder_left_x, 0.30, visibility=visibility)
    return landmarks


def test_every_lateral_point_has_an_anatomical_pair():
    """Mọi point ngoài mũi phải có hai index ứng viên, đủ để chọn phe theo ảnh.

    Bảng khóa theo point CHẴN (mỗi khóa là một cặp R/L); point lẻ là nửa còn lại.
    """
    even_ids = sorted(right for right, _ in POSE17_SIDE_PAIRS)
    assert sorted(POSE17_ANATOMICAL_PAIRS) == even_ids
    assert all(pid % 2 == 0 for pid in POSE17_ANATOMICAL_PAIRS)
    used: set[int] = set()
    static = {p.point_id: p.mediapipe for p in POSE17_POINTS}
    for right_id, pair in POSE17_ANATOMICAL_PAIRS.items():
        assert len(pair) == 2 and pair[0] != pair[1]
        assert set(pair) <= set(static.values())
        # Index tĩnh của lược đồ phải là một trong hai ứng viên của chính cặp đó.
        assert static[right_id] in pair
        used.update(pair)
    # Không index nào dùng cho hai khớp khác nhau.
    assert len(used) == 16


def test_nose_is_not_lateral_and_has_no_pair():
    assert 1 not in POSE17_ANATOMICAL_PAIRS
    assert POSE17_POINT_BY_ID[1].mediapipe == 0


def test_resolve_frame_side_puts_larger_x_index_into_even_point():
    """Point chẵn (R khung) phải lấy index có x lớn hơn, bất kể nhãn của model.

    Đây là hệ quả trực tiếp của guideline mục 2.1 và là lý do bỏ ánh xạ cố định:
    đo trên 24 ảnh thật cho thấy nhãn L/R của model chỉ đúng ~50%.
    """
    landmarks = _pose_landmarks(shoulder_right_x=0.35, shoulder_left_x=0.65)
    mapping, warnings = resolve_frame_side_indices(landmarks)
    # index 11 có x=0.65 (lớn hơn) nên vào point chẵn 6; index 12 vào point lẻ 7.
    assert mapping[6] == 11
    assert mapping[7] == 12
    assert warnings == []


def test_resolve_frame_side_follows_coordinates_not_model_labels():
    """Đảo toạ độ vai thì phép gán phải đảo theo — kể cả khi "nhãn model" đổi."""
    landmarks = _pose_landmarks(shoulder_right_x=0.65, shoulder_left_x=0.35)
    mapping, _ = resolve_frame_side_indices(landmarks)
    assert mapping[6] == 12, "index có x lớn hơn nay là 12, nên point 6 lấy 12"
    assert mapping[7] == 11


def test_resolve_frame_side_warns_when_two_sides_are_nearly_aligned():
    """Hai bên gần trùng trục ngang thì không phân được bên: cảnh báo, không đoán."""
    landmarks = _pose_landmarks(shoulder_right_x=0.50, shoulder_left_x=0.502)
    _, warnings = resolve_frame_side_indices(landmarks)
    assert any("không phân được trái/phải" in w for w in warnings)


def test_map_pose17_even_points_are_right_of_odd_points_on_real_geometry():
    """Bất biến trung tâm: mọi cặp R/L phải đúng thứ tự trái-phải trên khung hình."""
    landmarks = [RawLandmark(i, 0.5, 0.5, visibility=0.9) for i in range(33)]
    # Mỗi cặp: index lẻ ở x lớn, index chẵn ở x nhỏ — rồi map phải tự sửa lại.
    for offset, (odd, even) in enumerate(POSE17_ANATOMICAL_PAIRS.values()):
        landmarks[odd] = RawLandmark(odd, 0.60 + offset * 0.002, 0.50, visibility=0.9)
        landmarks[even] = RawLandmark(even, 0.40 - offset * 0.002, 0.50, visibility=0.9)

    report = map_pose17(PoseObservation(landmarks=landmarks), min_visibility=0.35)
    by_id = {p.point_id: p for p in report.points}
    for right_id, left_id in POSE17_SIDE_PAIRS:
        r, l = by_id[right_id], by_id[left_id]
        assert r.state != OUTSIDE and l.state != OUTSIDE
        assert r.x > l.x, f"point {right_id} (R) phải nằm bên phải point {left_id} (L)"


def test_map_pose17_warns_but_keeps_model_labels_when_sides_ambiguous():
    """Mặt chính diện: không đủ cơ sở phân bên thì giữ nhãn model + cảnh báo."""
    landmarks = [RawLandmark(i, 0.5, 0.5, visibility=0.9) for i in range(33)]
    report = map_pose17(PoseObservation(landmarks=landmarks), min_visibility=0.35)
    assert any("không phân được trái/phải" in w for w in report.warnings)
    by_id = {p.point_id: p for p in report.points}
    # Giữ nguyên index tĩnh của lược đồ.
    assert by_id[6].mediapipe == 11
    assert by_id[7].mediapipe == 12


def test_map_face50_returns_50_points():
    report = map_face50(FaceObservation(landmarks=_face_landmarks()))
    assert len(report.points) == 50
    assert sorted(p.point_id for p in report.points) == list(range(50))
    # Không có điểm nào bị bịa toạ độ: mọi điểm đều có x,y hữu hạn.
    for point in report.points:
        assert point.x == point.x and point.y == point.y


def test_map_pose17_marks_missing_landmarks_outside_not_zero_visible():
    """Nếu model không trả điểm, phải là Outside — không được giả vờ thấy ở (0,0)."""
    report = map_pose17(PoseObservation(landmarks=[]), min_visibility=0.35)
    assert len(report.points) == 17
    assert all(p.state == OUTSIDE for p in report.points)
    assert any("không đủ tin cậy" in w for w in report.warnings)
