"""Chuyển landmark thô của model thành điểm đúng lược đồ guideline.

Đây là tầng dễ sai nhất của cả tính năng, nên nó tách riêng và có test:

- **Gán trái/phải theo khung hình.** Guideline nói rõ R/L tính theo phía của
  ảnh, không theo giải phẫu người. MediaPipe lại đặt tên theo giải phẫu, nên hai
  bộ mắt/lông mày được gán lại bằng toạ độ x thật (``assign_face_sides``), và
  Pose-17 cũng chọn index theo toạ độ từng ảnh (``resolve_frame_side_indices``) —
  đo trên 24 ảnh thật cho thấy nhãn L/R của model chỉ khớp phía khung hình ~50%,
  nên không thể dùng một ánh xạ cố định.
- **Trạng thái Visible/Occluded/Outside** theo mục 4 của cả hai guideline.
- **Không bịa điểm.** Điểm model không thấy vẫn được trả về (để CVAT nhận đủ
  schema) nhưng mang trạng thái đúng, không bị đẩy sang một toạ độ giả.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..geometry import (
    FACE_POINTS,
    FACE_SIDE_GROUPS,
    FRAME_LEFT,
    FRAME_RIGHT,
    MOUTH_CORNERS,
    MOUTH_TARGET_RATIOS,
    MP_BROW_ANATOMICAL,
    MP_EYE_RING,
    MP_INNER_LIP_LOWER,
    MP_INNER_LIP_UPPER,
    MP_NOSE_MIDLINE_TOLERANCE,
    MP_NOSE_RIDGE_CHAIN,
    MP_OUTER_LIP_LOWER,
    MP_OUTER_LIP_UPPER,
    POSE17_ANATOMICAL_PAIRS,
    POSE17_POINTS,
    POSE17_SIDE_MIN_SPREAD,
    POSE17_SIDE_PAIRS,
    PointSpec,
)
from .mediapipe_pose import FaceObservation, PoseObservation, RawLandmark

# Trạng thái điểm, đúng property sẵn có của CVAT.
VISIBLE = "visible"
OCCLUDED = "occluded"
OUTSIDE = "outside"


@dataclass
class MappedPoint:
    """Một điểm đã sẵn sàng để ghi vào CVAT."""

    point_id: int
    name: str
    group: str
    x: float
    y: float
    state: str
    visibility: float = 1.0
    mediapipe: int | None = None
    note: str = ""

    @property
    def occluded(self) -> bool:
        return self.state == OCCLUDED

    @property
    def outside(self) -> bool:
        return self.state == OUTSIDE

    def as_dict(self) -> dict:
        return {
            "id": self.point_id,
            "name": self.name,
            "group": self.group,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "state": self.state,
            "visibility": round(self.visibility, 3),
            "mediapipe": self.mediapipe,
            "note": self.note,
        }


@dataclass
class MappingReport:
    """Kết quả map cho một ảnh, kèm cảnh báo để người dùng soi lại."""

    points: list[MappedPoint]
    warnings: list[str]
    rotation_applied: int = 0

    def by_group(self) -> dict[str, list[MappedPoint]]:
        grouped: dict[str, list[MappedPoint]] = {}
        for point in self.points:
            grouped.setdefault(point.group, []).append(point)
        return grouped

    def counts(self) -> dict[str, int]:
        result = {VISIBLE: 0, OCCLUDED: 0, OUTSIDE: 0}
        for point in self.points:
            result[point.state] = result.get(point.state, 0) + 1
        return result


# --------------------------------------------------------------------------- #
# trạng thái
# --------------------------------------------------------------------------- #
def classify_state(
    x: float,
    y: float,
    *,
    visibility: float,
    min_visibility: float,
    width: float = 1.0,
    height: float = 1.0,
    corner_guard: bool = True,
    margin: float = 0.02,
) -> tuple[str, str]:
    """Quyết định trạng thái theo mục 4 của guideline. Trả (state, note).

    Thứ tự áp dụng đúng như guideline: ngoài khung -> Outside; thấy trực tiếp ->
    Visible; suy ra được -> Occluded; không thì Outside.
    """
    if x < -margin or x > width + margin or y < -margin or y > height + margin:
        return OUTSIDE, "ngoài khung hình"

    # MediaPipe đẩy các khớp không đoán được về gần gốc toạ độ. Guideline mô tả
    # đúng hiện tượng này ("chùm điểm ở góc trên-trái"), nên nhận diện và đánh
    # Outside thay vì ghi một toạ độ vô nghĩa.
    if corner_guard and visibility < min_visibility and x <= 0.05 and y <= 0.05:
        return OUTSIDE, "model không đoán được (chùm điểm góc trên-trái)"

    if visibility < 0.05:
        return OUTSIDE, "model không thấy điểm"

    if visibility < min_visibility:
        return OCCLUDED, f"bị che (visibility {visibility:.2f})"

    return VISIBLE, ""


# --------------------------------------------------------------------------- #
# trái/phải theo khung hình
# --------------------------------------------------------------------------- #
def _mean_x(landmarks: list[RawLandmark], indices: tuple[int, ...]) -> float | None:
    values = [landmarks[i].x for i in indices if 0 <= i < len(landmarks)]
    if not values:
        return None
    return sum(values) / len(values)


def face_side_swap_needed(landmarks: list[RawLandmark]) -> tuple[bool, str]:
    """Có cần đổi chỗ hai bộ mắt/lông mày không?

    Trả ``(swap, lý do)``. Quyết định dựa trên toạ độ x của hai mắt theo giải
    phẫu: bộ nào nằm bên trái ảnh phải trở thành ``mattrai``/``longmaytrai``,
    bất kể MediaPipe gọi nó là mắt gì.
    """
    right_eye = _mean_x(landmarks, MP_EYE_RING[0])
    left_eye = _mean_x(landmarks, MP_EYE_RING[1])
    if right_eye is None or left_eye is None:
        return False, "thiếu dữ liệu mắt, giữ nguyên thứ tự MediaPipe"
    # MP_EYE_RING[0] là mắt PHẢI giải phẫu: nó phải nằm bên PHẢI khung hình.
    if right_eye < left_eye:
        return True, "mắt phải giải phẫu đang nằm bên trái ảnh, đã đổi chỗ theo khung hình"
    return False, ""


def _arc_ratios(landmarks: list[RawLandmark], chain: tuple[int, ...]) -> dict[int, float]:
    """Tỉ lệ cung của từng index trên một chuỗi, tính từ đầu chuỗi (0 -> 1)."""
    usable = [i for i in chain if 0 <= i < len(landmarks)]
    if len(usable) < 2:
        return {i: 0.0 for i in usable}
    cumulative = [0.0]
    for a, b in zip(usable, usable[1:]):
        cumulative.append(
            cumulative[-1]
            + math.hypot(landmarks[b].x - landmarks[a].x, landmarks[b].y - landmarks[a].y)
        )
    total = cumulative[-1]
    if total <= 0:
        return {i: 0.0 for i in usable}
    return {i: cumulative[k] / total for k, i in enumerate(usable)}


def pick_points_by_arc(
    landmarks: list[RawLandmark],
    chain: tuple[int, ...],
    targets: dict[int, float],
) -> dict[int, int]:
    """Chọn index cho từng point ID sao cho tỉ lệ cung gần ``targets`` nhất.

    Dùng cho môi: guideline cho tỉ lệ từng điểm dọc đường viền, mà vòng thật của
    MediaPipe có 20 điểm mỗi vòng, nên phải CHỌN ra bộ khớp tỉ lệ. Cách cũ cắt 12
    điểm đầu của vòng rồi quay theo x, khiến 5 điểm môi dưới dồn vào khoé phải.

    Chọn từng điểm theo tỉ lệ gần nhất, sau đó khử trùng bằng cách đẩy sang đỉnh
    kề còn trống. Không dùng "cửa sổ đơn điệu": làm vậy hai mục tiêu gần nhau sẽ
    tranh nhau một đỉnh và mục tiêu sau bị đẩy lệch rất xa.
    """
    ratios = _arc_ratios(landmarks, chain)
    usable = sorted(ratios, key=lambda i: ratios[i])
    if len(usable) < 2:
        return {}
    result: dict[int, int] = {}
    taken: set[int] = set()
    for point_id in sorted(targets, key=lambda pid: targets[pid]):
        target = targets[point_id]
        order = sorted(usable, key=lambda i: (abs(ratios[i] - target), ratios[i], i))
        chosen = next((i for i in order if i not in taken), None)
        if chosen is None:
            continue
        taken.add(chosen)
        result[point_id] = chosen
    return result


def _pick_nose_bridge(landmarks: list[RawLandmark]) -> dict[int, int]:
    """Chọn 4 điểm sống mũi 10..13 chia đều theo cung, bám trục giữa mặt.

    Bản cũ dùng thẳng (168, 6, 197, 195): đo trên job 2214, bộ này dừng ở y=349
    trong khi nasion ở y=324 và chóp mũi ở y=377, tức sống mũi chỉ dài 27/53px.
    Reviewer đã nêu đúng: "khương mũi quá ngắn so với thực tế".
    """
    usable = [i for i in MP_NOSE_RIDGE_CHAIN if 0 <= i < len(landmarks)]
    if len(usable) < 2:
        return {}

    # Chuỗi gốc chỉ có 5 đỉnh thật nên khoảng cách giữa chúng không đều; đục thêm
    # để 4 điểm chia đều theo cung mà vẫn bám trục giữa mặt.
    dense: list[int] = []
    midline = (landmarks[usable[0]].x + landmarks[usable[-1]].x) / 2
    for a, b in zip(usable, usable[1:]):
        dense.append(a)
        length = math.hypot(
            landmarks[b].x - landmarks[a].x, landmarks[b].y - landmarks[a].y
        )
        steps = max(1, int(length * 200))
        for k in range(1, steps):
            t = k / steps
            x = landmarks[a].x + (landmarks[b].x - landmarks[a].x) * t
            y = landmarks[a].y + (landmarks[b].y - landmarks[a].y) * t
            best = min(
                range(len(landmarks)),
                key=lambda i: (landmarks[i].x - x) ** 2 + (landmarks[i].y - y) ** 2,
            )
            # Chỉ nhận đỉnh còn nằm trong dải sống mũi; nếu không có thì bỏ qua
            # bước này thay vì kéo điểm lệch sang cánh mũi.
            if abs(landmarks[best].x - midline) <= MP_NOSE_MIDLINE_TOLERANCE:
                dense.append(best)
    dense.append(usable[-1])

    ratios = _arc_ratios(landmarks, tuple(dense))
    result: dict[int, int] = {}
    for k in range(4):
        target = k / 3
        pixel = min(dense, key=lambda i: (abs(ratios[i] - target), ratios[i]))
        result[10 + k] = pixel
    return result


def assign_face_sides(landmarks: list[RawLandmark]) -> tuple[dict[int, int], list[str]]:
    """Gán index MediaPipe cho từng point ID của bài mặt.

    Trả về ``(point_id -> mediapipe index, warnings)``.

    Mắt và lông mày được gán **theo toạ độ x thật** chứ không theo tên gọi của
    MediaPipe: bộ nào nằm bên trái ảnh thì vào ``mattrai``/``longmaytrai``. Nhờ
    vậy quy ước trái/phải theo khung hình của guideline luôn đúng, kể cả khi mặt
    quay nghiêng hoặc ảnh bị lật. Mũi chọn theo cung trên trục giữa; miệng chọn
    theo tỉ lệ cung trên hai nửa vòng thật của MediaPipe.
    """
    warnings: list[str] = []

    def xs(indices: tuple[int, ...]) -> float:
        values = [landmarks[i].x for i in indices if i < len(landmarks)]
        return sum(values) / len(values) if values else 0.0

    eye_sets = sorted(MP_EYE_RING, key=xs)
    brow_sets = sorted(MP_BROW_ANATOMICAL, key=xs)

    # Nếu thứ tự thật ngược với tên giải phẫu của MediaPipe thì báo, vì đó là dấu
    # hiệu ảnh/mặt bị lật và người dùng nên biết.
    if xs(MP_EYE_RING[0]) < xs(MP_EYE_RING[1]):
        warnings.append("mắt phải giải phẫu đang nằm bên trái ảnh, đã gán lại theo khung hình")

    mapping: dict[int, int] = {}

    # Lông mày 0-9. Guideline mục 3.1 mô tả longmaytrai "chạy từ ngoài vào trong",
    # nhưng mục 5.2 đòi "toạ độ x của các điểm 0 đến 9 TĂNG DẦN" và mục 3.1 chốt:
    # "khi mặt gần chính diện, toạ độ x của 10 điểm này tăng dần liên tục từ 0 đến 9".
    #
    # Đo trên 5 frame thật job 2214 (work/check_vf50_rerun.py): bản cũ sắp nhóm
    # trái GIẢM dần nên x của 0..9 đi xuống ở cả 4 chặng đầu — hỏng mục 5.2 ở 5/5
    # frame, đúng thứ reviewer nhìn ra. Nay sắp CẢ HAI nhóm tăng dần theo x:
    # 0 = trái nhất khung (đuôi ngoài mày trái), 9 = phải nhất (đuôi ngoài mày phải).
    brow_frame_left = sorted(brow_sets[0], key=lambda i: landmarks[i].x if i < len(landmarks) else 0)
    brow_frame_right = sorted(brow_sets[1], key=lambda i: landmarks[i].x if i < len(landmarks) else 0)
    for offset, index in enumerate(brow_frame_left):
        mapping[0 + offset] = index
    for offset, index in enumerate(brow_frame_right):
        mapping[5 + offset] = index

    # Sống mũi 10-13, chia đều theo cung trên trục giữa mặt.
    mapping.update(_pick_nose_bridge(landmarks))

    # Mắt: contour phải bắt đầu ở điểm trái nhất của mắt, chạy dọc mí trên sang
    # điểm phải nhất rồi vòng về theo mí dưới (guideline mục 3.3). Bộ trái khung
    # hình vào mattrai (14-21), bộ phải khung hình vào matphai (22-29).
    # `eye_sets` đã sắp theo x, nên bộ [0] là mắt trái khung hình -> base 14.
    for base, contour in ((14, eye_sets[0]), (22, eye_sets[1])):
        for offset, index in enumerate(order_eye_contour(landmarks, contour)):
            mapping[base + offset] = index

    # Miệng: khoé 30/36 (ngoài) và 42/46 (trong) lấy theo bảng; 5 điểm mỗi nửa môi
    # ngoài và 3 điểm mỗi nửa môi trong chọn theo TỈ LỆ CUNG trên nửa vòng thật.
    # Khoé trái khung hình phải là điểm 30/42, nên nếu MediaPipe trả ngược thì đổi
    # hai khoé cho nhau (vòng vẫn giữ nguyên thứ tự, chỉ đổi chiều đọc).
    outer_left, outer_right = MOUTH_CORNERS[30], MOUTH_CORNERS[36]
    inner_left, inner_right = MOUTH_CORNERS[42], MOUTH_CORNERS[46]
    if (
        outer_left < len(landmarks)
        and outer_right < len(landmarks)
        and landmarks[outer_left].x > landmarks[outer_right].x
    ):
        warnings.append("khoé môi trái/phải của MediaPipe ngược khung hình, đã đổi chiều đọc")
        outer_left, outer_right = outer_right, outer_left
        inner_left, inner_right = inner_right, inner_left

    outer_upper = (
        MP_OUTER_LIP_UPPER if MP_OUTER_LIP_UPPER[0] == outer_left else tuple(reversed(MP_OUTER_LIP_UPPER))
    )
    outer_lower = (
        MP_OUTER_LIP_LOWER if MP_OUTER_LIP_LOWER[0] == outer_right else tuple(reversed(MP_OUTER_LIP_LOWER))
    )
    inner_upper = (
        MP_INNER_LIP_UPPER if MP_INNER_LIP_UPPER[0] == inner_left else tuple(reversed(MP_INNER_LIP_UPPER))
    )
    inner_lower = (
        MP_INNER_LIP_LOWER if MP_INNER_LIP_LOWER[0] == inner_right else tuple(reversed(MP_INNER_LIP_LOWER))
    )

    mapping[30] = outer_left
    mapping[36] = outer_right
    mapping[42] = inner_left
    mapping[46] = inner_right

    edges = {
        30: outer_upper,
        36: outer_lower,
        42: inner_upper,
        46: inner_lower,
    }
    chain_of: dict[int, tuple[int, ...]] = {}
    for point_id in (31, 32, 33, 34, 35):
        chain_of[point_id] = edges[30]
    for point_id in (37, 38, 39, 40, 41):
        chain_of[point_id] = edges[36]
    for point_id in (43, 44, 45):
        chain_of[point_id] = edges[42]
    for point_id in (47, 48, 49):
        chain_of[point_id] = edges[46]

    # Mỗi nửa vòng có 11 index; đầu và cuối là hai khoé nên chỉ chọn ở giữa. Gom
    # theo nửa vòng rồi chọn MỘT LẦN để việc khử trùng không đẩy hai điểm chồng nhau.
    for edge_corner in (30, 36, 42, 46):
        ids = [pid for pid, chain in chain_of.items() if chain is edges[edge_corner]]
        if not ids:
            continue
        picked = pick_points_by_arc(
            landmarks,
            edges[edge_corner][1:-1],
            {pid: MOUTH_TARGET_RATIOS[pid] for pid in ids},
        )
        mapping.update(picked)

    return mapping, warnings


def _eye_chains(landmarks: list[RawLandmark], ring: tuple[int, ...]):
    """Chọn 3 điểm mí trên + 3 điểm mí dưới từ VÒNG 16 đỉnh, quanh 2 khoé.

    Trả ``(left, right, upper, lower)``. Cả hai chuỗi trả về đã sắp theo x để nối
    vòng không bắt chéo.

    Vì sao phải CHỌN chứ không lấy sẵn: guideline mô tả mỗi mắt là "2 khoé + 3 mí
    trên + 3 mí dưới", nhưng vòng 16 đỉnh của MediaPipe KHÔNG chia sẵn như vậy —
    hai khoé là ngã ba, và các đỉnh còn lại không tách thành 5+5 theo chỉ số. Bản
    trước lấy thẳng 8 chỉ số nên vô tình gán điểm mí dưới vào mí trên, và thứ tự
    dựng ra bị vặn (đã lộ ra trên mặt thật ở job CVAT 2214).
    """
    usable = [i for i in ring if 0 <= i < len(landmarks)]
    if len(usable) < 6:
        return None
    left = min(usable, key=lambda i: (landmarks[i].x, landmarks[i].y, i))
    right = max(usable, key=lambda i: (landmarks[i].x, -landmarks[i].y, -i))
    if left == right:
        return None

    ax, ay = landmarks[left].x, landmarks[left].y
    bx, by = landmarks[right].x, landmarks[right].y
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return None

    def side(index: int) -> float:
        # Tích có hướng; trong hệ toạ độ ảnh (y hướng xuống) âm = phía trên đường
        # nối hai khoé, tức mí trên.
        return dx * (landmarks[index].y - ay) - dy * (landmarks[index].x - ax)

    middle_x = (ax + bx) / 2
    span = abs(bx - ax) or 1.0
    candidates = [i for i in usable if i not in (left, right)]

    def pick(upper: bool) -> list[int]:
        pool = [i for i in candidates if (side(i) < 0) == upper]
        # Điểm mí THẬT nằm gần giữa mắt theo trục x (đó là nơi mí trên cao nhất và
        # mí dưới thấp nhất, đúng câu chữ guideline). Chỉ lấy "xa đường nối hai khoé
        # nhất" là sai: hai khoé nằm ngay trên đường đó, nên điểm gần khoé cũng xa
        # và bị chọn nhầm — đã lộ ra trên mặt thật ở job 2214.
        # Điểm số: ưu tiên gần giữa mắt, phụ thuộc độ xa đường cơ sở.
        pool.sort(
            key=lambda i: (
                abs(landmarks[i].x - middle_x) / span,
                -abs(side(i)),
                i,
            )
        )
        chosen = pool[:3]
        if len(chosen) < 3:
            rest = sorted(
                (i for i in candidates if i not in chosen),
                key=lambda i: (abs(landmarks[i].x - middle_x) / span, -abs(side(i)), i),
            )
            chosen += rest[: 3 - len(chosen)]
        chosen.sort(key=lambda i: landmarks[i].x, reverse=not upper)
        return chosen

    return left, right, pick(True), pick(False)


def order_eye_contour(landmarks: list[RawLandmark], indices: tuple[int, ...]) -> tuple[int, ...]:
    """Dựng lại thứ tự contour mắt đúng guideline mục 3.3.

    Quy tắc của guideline: điểm đầu là điểm trái nhất của mắt, chạy dọc **mí trên**
    sang điểm phải nhất, rồi vòng về theo **mí dưới**. Điều kiện kiểm tra được mà
    guideline nêu — "contour không có đường bắt chéo tạo thành hình chữ X" — chỉ
    đúng khi hai chuỗi mí không trộn vào nhau.

    ``indices`` nên là **vòng 16 đỉnh** (``MP_EYE_RING``). Nếu truyền một tập con
    thì hàm vẫn chạy nhưng chất lượng kém hơn, vì có ít ứng viên để chọn mí.

    Không thể lấy thứ tự này bằng cách sắp xếp theo x: làm vậy sẽ xen kẽ mí trên
    với mí dưới và tạo đúng hình chữ X mà guideline cấm.
    """
    chosen = _eye_chains(landmarks, tuple(indices))
    if chosen is None:
        return tuple(sorted((i for i in indices if 0 <= i < len(landmarks)), key=lambda i: landmarks[i].x))
    left, right, upper, lower = chosen
    return tuple([left, *upper, right, *lower])


# --------------------------------------------------------------------------- #
# map công khai
# --------------------------------------------------------------------------- #
def resolve_frame_side_indices(
    landmarks: list[RawLandmark],
) -> tuple[dict[int, int], list[str]]:
    """Chọn, cho TỪNG ảnh, index nào vào point chẵn (R khung) và point lẻ (L khung).

    Guideline mục 2.1 chỉ đòi một điều: "điểm R nằm ở phía phải của ảnh đang hiển
    thị". Đo trên 24 ảnh người lái thật cho thấy **không** ánh xạ index cố định nào
    đạt được điều đó — nhãn L/R của MediaPipe chỉ khớp phía khung hình ~50%, và
    trong cùng một ảnh hai khớp khác nhau có thể ngược nhau. Vì vậy ở đây chọn
    theo toạ độ: trong hai index của cùng một khớp, index nào có x LỚN HƠN thì vào
    point chẵn (phía phải khung), index còn lại vào point lẻ.

    Khi hai index gần như trùng x (mặt nhìn thẳng, ảnh chính diện), không có cơ sở
    hình học nào để phân bên; giữ nhãn của model và trả cảnh báo thay vì đoán.

    Trả ``({point_id: index}, cảnh báo)``.
    """
    mapping: dict[int, int] = {}
    warnings: list[str] = []
    ambiguous: list[str] = []
    for spec in POSE17_POINTS:
        # Bảng chỉ khóa theo point CHẴN; point lẻ là nửa còn lại của cùng cặp.
        even_id = spec.point_id if spec.point_id % 2 == 0 else spec.point_id - 1
        pair = POSE17_ANATOMICAL_PAIRS.get(even_id)
        if pair is None or spec.mediapipe is None:
            # Điểm giữa (mũi) hoặc khớp không có cặp: dùng index tĩnh.
            mapping[spec.point_id] = spec.mediapipe
            continue
        first, second = pair
        if first >= len(landmarks) or second >= len(landmarks):
            mapping[spec.point_id] = spec.mediapipe
            continue
        if abs(landmarks[first].x - landmarks[second].x) < POSE17_SIDE_MIN_SPREAD:
            # Không phân được bên: giữ nguyên nhãn model cho cặp này.
            mapping[spec.point_id] = spec.mediapipe
            ambiguous.append(spec.name)
            continue
        # point chẵn = bên PHẢI khung = index có x lớn hơn.
        frame_right = first if landmarks[first].x > landmarks[second].x else second
        frame_left = second if frame_right == first else first
        mapping[spec.point_id] = frame_right if spec.point_id % 2 == 0 else frame_left

    if ambiguous:
        warnings.append(
            "hai bên gần như trùng trục ngang nên không phân được trái/phải theo "
            f"khung hình cho điểm {', '.join(ambiguous)}; đã giữ nhãn của model — "
            "hãy soi lại bằng mắt"
        )
    return mapping, warnings


def map_pose17(
    observation: PoseObservation,
    *,
    min_visibility: float = 0.35,
    wid: float = 1.0,
    hei: float = 1.0,
) -> MappingReport:
    """Map một ``PoseObservation`` thành 17 điểm theo guideline HumanPose-17.

    Trái/phải theo **khung hình** (guideline mục 2.1): point chẵn phải nằm phía
    phải khung hình. Index MediaPipe cho từng point được chọn theo toạ độ của chính
    ảnh này — xem ``resolve_frame_side_indices`` để biết vì sao không thể dùng một
    ánh xạ cố định.
    """
    landmarks = observation.landmarks
    warnings: list[str] = []
    landmark_ok = len(landmarks) >= 29
    if not landmark_ok:
        warnings.append(f"chỉ có {len(landmarks)} landmark, cần >=29 để map đủ 17 điểm")

    side_map, side_warnings = resolve_frame_side_indices(landmarks)
    warnings.extend(side_warnings)

    points: list[MappedPoint] = []
    for spec in POSE17_POINTS:
        index = side_map.get(spec.point_id, spec.mediapipe)
        if index is None or index >= len(landmarks):
            points.append(
                MappedPoint(
                    point_id=spec.point_id,
                    name=spec.name,
                    group=spec.group,
                    x=0.0,
                    y=0.0,
                    state=OUTSIDE,
                    mediapipe=index,
                    note="model không trả điểm này",
                )
            )
            continue
        landmark = landmarks[index]
        state, note = classify_state(
            landmark.x,
            landmark.y,
            visibility=landmark.visibility,
            min_visibility=min_visibility,
            width=wid,
            height=hei,
        )
        points.append(
            MappedPoint(
                point_id=spec.point_id,
                name=spec.name,
                group=spec.group,
                x=landmark.x * wid,
                y=landmark.y * hei,
                state=state,
                visibility=landmark.visibility,
                mediapipe=index,
                note=note,
            )
        )

    if not landmark_ok:
        warnings.append("kết quả pose không đủ tin cậy, nên kiểm tra lại bằng mắt")
    return MappingReport(points=points, warnings=warnings, rotation_applied=observation.rotation_applied)


def map_face50(
    observation: FaceObservation,
    *,
    min_visibility: float = 0.35,
    wid: float = 1.0,
    hei: float = 1.0,
) -> MappingReport:
    """Map một ``FaceObservation`` thành 50 điểm theo guideline VF-50.

    Lưu ý: FaceMesh không trả ``visibility`` cho từng điểm, nên mọi điểm đều là
    Visible trừ khi rơi ra ngoài khung. Guideline cũng mô tả đúng như vậy — phần
    trạng thái trong bài mặt "coi như chưa ai làm" và phải do người xem quyết
    định. Ở đây ``min_visibility`` vì thế chỉ có tác dụng chặn toạ độ vô lý.
    """
    landmarks = observation.landmarks
    warnings: list[str] = []
    if len(landmarks) < 468:
        warnings.append(f"chỉ có {len(landmarks)} landmark, cần >=468 cho FaceMesh")

    mapping, side_warnings = assign_face_sides(landmarks)
    warnings.extend(side_warnings)

    points: list[MappedPoint] = []
    for spec in FACE_POINTS:
        index = mapping.get(spec.point_id)
        if index is None or index >= len(landmarks):
            points.append(
                MappedPoint(
                    point_id=spec.point_id,
                    name=spec.name,
                    group=spec.group,
                    x=0.0,
                    y=0.0,
                    state=OUTSIDE,
                    mediapipe=index,
                    note="model không trả điểm này",
                )
            )
            continue
        landmark = landmarks[index]
        state, note = classify_state(
            landmark.x,
            landmark.y,
            visibility=1.0,
            min_visibility=0.0,
            width=wid,
            height=hei,
            corner_guard=False,
        )
        points.append(
            MappedPoint(
                point_id=spec.point_id,
                name=spec.name,
                group=spec.group,
                x=landmark.x * wid,
                y=landmark.y * hei,
                state=state,
                visibility=1.0,
                mediapipe=index,
                note=note,
            )
        )

    warnings.extend(face_side_conflicts(landmarks, mapping))
    return MappingReport(points=points, warnings=warnings, rotation_applied=observation.rotation_applied)


def face_side_conflicts(landmarks: list[RawLandmark], mapping: dict[int, int]) -> list[str]:
    """Kiểm tra R/L sau khi gán. Trả về cảnh báo nếu nhóm *trai nằm bên phải ảnh.

    Soát **cả nhóm** điểm (không phải 4 điểm đầu), vì mục 2.1 của guideline yêu
    cầu giữ đúng thứ tự không gian trái -> phải trên toàn bộ nhóm landmark.
    """
    warnings: list[str] = []
    for left_group, right_group, left_base, right_base in FACE_SIDE_GROUPS:
        left_ids = [pid for pid in mapping if _group_span(left_group) [0] <= pid <= _group_span(left_group)[1]]
        right_ids = [
            pid for pid in mapping if _group_span(right_group)[0] <= pid <= _group_span(right_group)[1]
        ]
        # Nhóm dùng chung một label (moingoai/moitrong) thì tách theo nửa dãy.
        if left_group == right_group:
            span = sorted(left_ids)
            half = len(span) // 2
            left_ids, right_ids = span[:half], span[half:]
        left_x = [landmarks[mapping[pid]].x for pid in left_ids if mapping.get(pid) is not None]
        right_x = [landmarks[mapping[pid]].x for pid in right_ids if mapping.get(pid) is not None]
        if not left_x or not right_x:
            continue
        if sum(left_x) / len(left_x) > sum(right_x) / len(right_x):
            warnings.append(
                f"nghi ngờ đảo trái/phải giữa {left_group} và {right_group} "
                f"(x trái {sum(left_x) / len(left_x):.3f} > x phải {sum(right_x) / len(right_x):.3f})"
            )
    return warnings


def _group_span(group: str) -> tuple[int, int]:
    """Khoảng point ID của một nhóm trong lược đồ VF-50."""
    spans = {
        "longmaytrai": (0, 4),
        "longmayphai": (5, 9),
        "songmui": (10, 13),
        "mattrai": (14, 21),
        "matphai": (22, 29),
        "moingoai": (30, 41),
        "moitrong": (42, 49),
    }
    return spans.get(group, (0, -1))


def describe(report: MappingReport) -> str:
    """Mô tả ngắn gọn để in ra log/CLI."""
    counts = report.counts()
    lines = [
        f"{len(report.points)} điểm: "
        f"visible={counts.get(VISIBLE, 0)} "
        f"occluded={counts.get(OCCLUDED, 0)} "
        f"outside={counts.get(OUTSIDE, 0)}"
    ]
    if report.rotation_applied:
        lines.append(f"đã xoay ảnh {report.rotation_applied}° trước khi suy luận")
    for warning in report.warnings:
        lines.append(f"cảnh báo: {warning}")
    return "\n".join(lines)


__all__ = [
    "VISIBLE",
    "OCCLUDED",
    "OUTSIDE",
    "MappedPoint",
    "MappingReport",
    "classify_state",
    "assign_face_sides",
    "order_eye_contour",
    "face_side_swap_needed",
    "resolve_frame_side_indices",
    "map_pose17",
    "map_face50",
    "describe",
    "FRAME_LEFT",
    "FRAME_RIGHT",
]
