"""Lược đồ điểm cho hai bài Week 2: Face Landmark VF-50 và HumanPose-17.

Nguồn sự thật của lược đồ là hai guideline gốc trong `guildlline/`; bảng
MediaPipe chỉ là *ánh xạ suy diễn* từ model về đúng ID của guideline.

Ba quy tắc của guideline được mã hoá cứng ở đây, vì vi phạm chúng là sai bài
chứ không phải sai kỹ thuật:

1. **Point ID không được đổi.** VF-50 chạy ID 0-49 liên tục qua cả 7 skeleton
   (`mattrai` dùng 14-21, KHÔNG phải 0-7). Pose-17 đặt tên sublabel là chuỗi số
   "1".."17". Không remap sang WFLW / COCO / MediaPipe.
2. **Trái/phải theo phía của ảnh**, không theo giải phẫu người. Vì vậy mỗi điểm
   khai báo `frame_side` = phía mà nó phải nằm trên khung hình.
3. **Trạng thái dùng property sẵn có của CVAT** (`outside`, `occluded`), không
   tạo attribute mới, không dùng Hidden.

Ánh xạ MediaPipe có một điểm dễ sai: MediaPipe gọi tên mắt/lông mày theo **giải
phẫu người**, còn guideline gọi theo **phía khung hình**. Hai quy ước này chỉ
trùng nhau khi mặt nhìn thẳng. Vì vậy bảng dưới đây giữ *cả hai bộ* mắt/lông mày
(`MP_*_ANATOMICAL`) và tầng `geometry` tự gán lại theo toạ độ x thật của ảnh —
không tin vào tên gọi của model.
"""

from __future__ import annotations

from dataclasses import dataclass

FRAME_LEFT = "left"
FRAME_RIGHT = "right"
FRAME_CENTER = "center"


@dataclass(frozen=True)
class PointSpec:
    """Một điểm trong lược đồ guideline."""

    point_id: int
    name: str
    group: str
    frame_side: str = FRAME_CENTER
    #: index MediaPipe tương ứng; None nghĩa là model không có điểm này.
    mediapipe: int | None = None

    @property
    def sublabel(self) -> str:
        """Tên sublabel đúng như guideline yêu cầu (luôn là chuỗi số)."""
        return self.name


@dataclass(frozen=True)
class SkeletonSpec:
    """Một skeleton: Pose-17 có 1, Face VF-50 có 7."""

    name: str
    closed: bool
    point_ids: tuple[int, ...]
    label_name: str = ""
    edges: tuple[tuple[int, int], ...] = ()

    def resolved_label(self) -> str:
        return self.label_name or self.name


# ==========================================================================
# HumanPose-17 — một skeleton tên `person`, sublabel "1".."17"
# ==========================================================================
# Guideline mục 2.2: thứ tự không được đổi.
POSE17_HUMAN_NAMES: tuple[str, ...] = (
    "Nose", "R Eye", "L Eye", "R Ear", "L Ear",
    "R Shoulder", "L Shoulder", "R Elbow", "L Elbow",
    "R Wrist", "L Wrist", "R Hip", "L Hip",
    "R Knee", "L Knee", "R Ankle", "L Ankle",
)

# Guideline mục 2.1 chốt quy ước theo KHUNG HÌNH: "Điểm R nằm ở phía phải của ảnh
# đang hiển thị; điểm L nằm ở phía trái của ảnh. Không suy luận theo tay/chân giải
# phẫu của người lái."
#
# Người lái quay mặt về camera, nên phía GIẢI PHẪU PHẢI của họ nằm ở bên TRÁI khung
# hình và ngược lại. MediaPipe Pose đặt nhãn theo giải phẫu (index 12 = "right
# shoulder"). Hệ quả: point chẵn (R theo khung hình) phải lấy landmark GIẢI PHẪU
# TRÁI, và point lẻ (L theo khung hình) phải lấy landmark GIẢI PHẪU PHẢI.
#
# Đây là lỗi thật đã đo được: bản trước gán index 12 (giải phẫu phải) cho point 6
# "R Shoulder", tức đặt điểm R ở bên TRÁI khung hình — ngược thẳng guideline. Đo
# trên landmark thật (work/pose_axis_probe.py): cả 8 cặp khớp của hai mẫu đều ngược.
#
# LƯU Ý về TAI: MediaPipe KHÔNG theo quy luật chẵn/lẻ ở index tai — 7 là tai TRÁI
# giải phẫu và 8 là tai PHẢI, ngược với vai/mắt. Đã kiểm trên mẫu thật
# work/wm_pose.json: idx7 x=0.666 > idx8 x=0.652, cùng chiều với vai
# (idx11 x=0.656 > idx12 x=0.595). Vì vậy 4/5 map theo quy luật, riêng tai map
# theo bằng chứng đo được.
POSE17_POINTS: tuple[PointSpec, ...] = (
    PointSpec(1, "1", "head", FRAME_CENTER, mediapipe=0),      # Nose
    PointSpec(2, "2", "head", FRAME_RIGHT, mediapipe=6),       # R Eye  <- model L Eye
    PointSpec(3, "3", "head", FRAME_LEFT, mediapipe=3),        # L Eye  <- model R Eye
    PointSpec(4, "4", "head", FRAME_RIGHT, mediapipe=7),       # R Ear  <- model L Ear
    PointSpec(5, "5", "head", FRAME_LEFT, mediapipe=8),        # L Ear  <- model R Ear
    PointSpec(6, "6", "upper", FRAME_RIGHT, mediapipe=11),     # R Shoulder <- model L
    PointSpec(7, "7", "upper", FRAME_LEFT, mediapipe=12),      # L Shoulder <- model R
    PointSpec(8, "8", "upper", FRAME_RIGHT, mediapipe=13),     # R Elbow    <- model L
    PointSpec(9, "9", "upper", FRAME_LEFT, mediapipe=14),      # L Elbow    <- model R
    PointSpec(10, "10", "upper", FRAME_RIGHT, mediapipe=15),   # R Wrist    <- model L
    PointSpec(11, "11", "upper", FRAME_LEFT, mediapipe=16),    # L Wrist    <- model R
    PointSpec(12, "12", "lower", FRAME_RIGHT, mediapipe=23),   # R Hip      <- model L
    PointSpec(13, "13", "lower", FRAME_LEFT, mediapipe=24),    # L Hip      <- model R
    PointSpec(14, "14", "lower", FRAME_RIGHT, mediapipe=25),   # R Knee     <- model L
    PointSpec(15, "15", "lower", FRAME_LEFT, mediapipe=26),    # L Knee     <- model R
    PointSpec(16, "16", "lower", FRAME_RIGHT, mediapipe=27),   # R Ankle    <- model L
    PointSpec(17, "17", "lower", FRAME_LEFT, mediapipe=28),    # L Ankle    <- model R
)

# Guideline mục 5.3 — topology VF dùng để dựng `svg` của skeleton.
# Cạnh nối theo POINT ID, không theo index MediaPipe, nên topology không đổi khi
# gán lại trái/phải: 4-6 vẫn là "tai R nối vai R", chỉ khác là nay cả hai đều lấy
# landmark giải phẫu trái của model.
POSE17_EDGES: tuple[tuple[int, int], ...] = (
    (1, 2), (1, 3), (2, 4), (3, 5), (4, 6), (5, 7),
    (6, 7), (6, 12), (7, 13), (12, 13),
    (6, 8), (8, 10), (7, 9), (9, 11),
    (12, 14), (14, 16), (13, 15), (15, 17),
)

# Tên skeleton trên CVAT không suy ra được từ guideline: cùng một bài 17 điểm có
# thể được cấu hình thành label `body` (sublabel "1".."17", đúng quy ước VF) hoặc
# `person` (sublabel theo tên giải phẫu). Đã kiểm tra trên CVAT localhost: entry
# point đúng là `body`. Đừng ghim cứng một tên — hãy dò trong danh sách label.
POSE17_LABEL_CANDIDATES: tuple[str, ...] = ("body", "person")

#: Số sublabel mà schema HumanPose-17 hợp lệ phải có.
POSE17_SUBLABEL_COUNT = len(POSE17_POINTS)

POSE17_SKELETON = SkeletonSpec(
    name="person",
    closed=False,
    point_ids=tuple(range(1, 18)),
    label_name="body",
    edges=POSE17_EDGES,
)

#: Nhóm điểm mà guideline yêu cầu kiểm tra R/L theo khung hình.
POSE17_SIDE_PAIRS: tuple[tuple[int, int], ...] = (
    (2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13), (14, 15), (16, 17),
)

#: Với mỗi cặp điểm hai bên, HAI index MediaPipe có thể dùng, xếp theo thứ tự
#: ``(ứng viên cho point chẵn = R khung, ứng viên cho point lẻ = L khung)``.
#:
#: Vì sao cần bảng này: đo 24 ảnh người lái thật (work/pose_frame_rule_probe.py)
#: cho thấy nhãn L/R của MediaPipe chỉ khớp phía khung hình ~50% số lần, và giữa
#: các khớp trong CÙNG một ảnh cũng có thể ngược nhau (G01_B011: vai idx11 ở bên
#: phải khung, nhưng mắt idx6 cũng ở bên phải khung). Nghĩa là **không tồn tại**
#: một ánh xạ index cố định nào đúng cho mọi ảnh.
#:
#: Guideline mục 2.1 chỉ đòi điểm R nằm phía PHẢI khung hình. Muốn chắc chắn đạt
#: điều đó thì phải chọn index theo toạ độ của từng ảnh (`map_pose17` làm việc
#: này). Bảng dưới là nguồn sự thật cho "hai index nào là hai bên của cùng một
#: khớp", để tầng map không phải đoán.
POSE17_ANATOMICAL_PAIRS: dict[int, tuple[int, int]] = {
    2: (6, 3),      # R/L Eye      <- model L/R Eye
    4: (7, 8),      # R/L Ear      <- model L/R Ear  (MediaPipe đánh số ngược tai)
    6: (11, 12),    # R/L Shoulder <- model L/R Shoulder
    8: (13, 14),    # R/L Elbow
    10: (15, 16),   # R/L Wrist
    12: (23, 24),   # R/L Hip
    14: (25, 26),   # R/L Knee
    16: (27, 28),   # R/L Ankle
}

#: |x(index A) - x(index B)| nhỏ hơn mức này thì hai bên gần như trùng nhau theo
#: trục ngang (mặt nhìn thẳng, ảnh chụp chính diện) và không thể kết luận bên nào
#: nằm phía nào của khung. Khi đó giữ nhãn của model và cảnh báo, thay vì đoán.
POSE17_SIDE_MIN_SPREAD = 0.01


# ==========================================================================
# VF-50 Face Landmark — 7 skeleton, sublabel là point ID dạng chuỗi "0".."49"
# ==========================================================================
# --- MediaPipe FaceMesh (468 landmark) ---
# Lông mày: MP right brow chạy từ đuôi ngoài vào trong (46,53,52,65,55);
# MP left brow chạy từ trong ra ngoài (285,295,282,283,276).
# Mắt: mỗi mắt là contour 8 điểm bắt đầu ở khoé ngoài rồi vòng theo mí trên
# sang khoé trong và về theo mí dưới.
MP_BROW_ANATOMICAL: tuple[tuple[int, ...], tuple[int, ...]] = (
    (46, 53, 52, 65, 55),
    (285, 295, 282, 283, 276),
)
# VÒNG MẮT ĐẦY ĐỦ 16 đỉnh của MediaPipe (từ face_mesh_connections.py).
# Đây mới là nguồn đúng để chọn 8 điểm: 8 điểm "đẹp" không tồn tại sẵn trong mesh,
# phải CHỌN ra từ vòng 16 đỉnh theo hình học.
#
# Bằng chứng đã trả giá: bản trước dùng thẳng (33,246,161,160,159,158,157,133) và
# coi 159/158/157 là mí trên. Trên mặt thật (job CVAT 2214) ba điểm đó có y LỚN HƠN
# khoé, tức chúng nằm trên mí DƯỚI — contour bị vặn nên thứ tự dựng ra sai.
MP_EYE_RING: tuple[tuple[int, ...], tuple[int, ...]] = (
    (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246),
    (263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466),
)
#: Hai khoé của mỗi mắt trong vòng trên (khoé ngoài, khoé trong).
MP_EYE_CORNERS: tuple[tuple[int, int], tuple[int, int]] = (
    (33, 133),    # MP right eye: ngoài (thái dương), trong (mũi)
    (263, 362),   # MP left eye
)

# Tập 8 điểm "gợi ý" giữ lại để tương thích ngược với test cũ. KHÔNG dùng tập này để
# suy luận thứ tự — hãy dùng `MP_EYE_RING` + `order_eye_contour`.
MP_EYE_ANATOMICAL: tuple[tuple[int, ...], tuple[int, ...]] = (
    (33, 246, 161, 160, 159, 158, 157, 133),   # MP right eye
    (263, 466, 388, 387, 386, 385, 384, 362),  # MP left eye
)

# --- Sống mũi (đục lại) -----------------------------------------------------
# Bản cũ dùng (168, 6, 197, 195) và DỪNG ở y=349, trong khi nasion y=324 và chóp
# mũi y=377 — tức sống mũi chỉ dài 27/53px (51%). Reviewer đã nhìn ra: "khương mũi
# quá ngắn so với thực tế". Bộ mới trải hết chiều dài sống mũi tới chóp.
#
# Chuỗi dày dọc trục giữa từ nasion (168) tới chóp mũi (44), đục từ các đỉnh mesh
# thật đã đo trên job CVAT 2214 (work/diag_nose_brow.py):
#   idx168 y=324 | idx6 y=334 | idx197 y=341 | idx51 y=359 | idx44 y=378
# Bốn điểm 10..13 được chọn chia đều theo cung trên chuỗi này.
MP_NOSE_RIDGE_CHAIN: tuple[int, ...] = (168, 6, 197, 51, 44)

#: Nửa bề rộng tối đa (px) mà một đỉnh còn được coi là nằm trên sống mũi.
#: Mũi rộng ~30px nên 8px vẫn nằm trong dải sống, không lấn sang cánh mũi.
MP_NOSE_MIDLINE_TOLERANCE = 8.0

# --- Môi (đục lại) ---------------------------------------------------------
# Vòng môi THẬT của MediaPipe có 20 điểm mỗi vòng (môi ngoài) và 20 điểm (môi
# trong), lấy từ `FaceLandmarksConnections.FACE_LANDMARKS_LIPS` (40 cạnh = 2 vòng
# 20 cạnh). Bản cũ cắt 12 điểm đầu của vòng ngoài rồi quay theo x, nên 5 điểm môi
# dưới rơi hết vào vùng khoé phải: đo trên job 2214 chỉ dùng index {267..291},
# bỏ trắng nửa môi dưới. Đó đúng là "nối bị sai rất nhiều" reviewer nêu.
#
# Hai chuỗi dưới đây là hai NỬA VÒNG theo đúng thứ tự kết nối của MediaPipe, mỗi
# chuỗi chạy từ khoé trái sang khoé phải. Điểm 30/36 (và 42/46) là hai đầu chuỗi.
MP_OUTER_LIP_UPPER: tuple[int, ...] = (
    61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291,
)
MP_OUTER_LIP_LOWER: tuple[int, ...] = (
    291, 375, 321, 405, 314, 17, 84, 181, 91, 146, 61,
)
MP_INNER_LIP_UPPER: tuple[int, ...] = (
    78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308,
)
MP_INNER_LIP_LOWER: tuple[int, ...] = (
    308, 324, 318, 402, 317, 14, 87, 178, 88, 95, 78,
)

#: Ai cũng phải khép vòng từ khoé phải về khoé trái; kiểm lúc import để không ai
#: sửa nửa vòng mà quên nửa kia.
_LIP_CORNERS: tuple[tuple[tuple[int, ...], tuple[int, ...], int, int], ...] = (
    (MP_OUTER_LIP_UPPER, MP_OUTER_LIP_LOWER, 61, 291),
    (MP_INNER_LIP_UPPER, MP_INNER_LIP_LOWER, 78, 308),
)
for _upper, _lower, _left, _right in _LIP_CORNERS:
    assert _upper[0] == _left and _upper[-1] == _right, "nửa vòng môi trên sai khoé"
    assert _lower[0] == _right and _lower[-1] == _left, "nửa vòng môi dưới sai khoé"

# Tỉ lệ guideline mục 3.4, quy về [0,1] tính từ KHOÉ TRÁI dọc nửa vòng.
# Guideline đo môi dưới NGƯỢC CHIỀU (từ khoé phải, tỉ lệ 0.18 -> 0.87), nên đã đổi
# thành 1-x cho khớp chiều đọc của `MP_OUTER_LIP_LOWER` (khoé phải -> khoé trái).
# Bộ số này là mô tả tương đối: đo lại trên mesh thấy cung thật hơi khác, nên chỗ
# dùng chỉ khớp theo THỨ TỰ và tính đơn điệu, không đòi khớp tuyệt đối.
MOUTH_TARGET_RATIOS: dict[int, float] = {
    # môi ngoài, nửa trên: 31..35, đo từ khoé trái (61)
    31: 0.18, 32: 0.41, 33: 0.53, 34: 0.65, 35: 0.85,
    # môi ngoài, nửa dưới: 37..41, đo từ khoé PHẢI (291)
    41: 0.13, 40: 0.30, 39: 0.47, 38: 0.65, 37: 0.82,
    # môi trong, nửa trên: 43..45, đo từ khoé trái (78)
    43: 0.22, 44: 0.53, 45: 0.82,
    # môi trong, nửa dưới: 47..49, đo từ khoé PHẢI (308)
    49: 0.19, 48: 0.47, 47: 0.77,
}

#: Điểm khoé của môi: point ID -> (index MediaPipe, thuộc vòng ngoài hay trong).
MOUTH_CORNERS: dict[int, int] = {30: 61, 36: 291, 42: 78, 46: 308}

# --- Bộ index CŨ, chỉ giữ để tương thích ngược -------------------------------
# `landmarks.assign_face_sides` KHÔNG còn dùng ba hằng số dưới đây. Giữ lại vì
# test cũ và `all_face_mediapipe_indices` còn tham chiếu; đừng dùng cho map mới.
#: @deprecated dùng `MP_NOSE_RIDGE_CHAIN`.
MP_NOSE_BRIDGE: tuple[int, ...] = (168, 6, 197, 195)
#: @deprecated dùng `MP_OUTER_LIP_UPPER`/`MP_OUTER_LIP_LOWER`.
MP_OUTER_MOUTH: tuple[int, ...] = (61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 146)
#: @deprecated dùng `MP_INNER_LIP_UPPER`/`MP_INNER_LIP_LOWER`.
MP_INNER_MOUTH: tuple[int, ...] = (78, 80, 81, 82, 312, 311, 310, 308)

# Cấu trúc lược đồ VF-50: mỗi entry là (point_id, group, frame_side).
# MediaPipe không có sẵn trong bảng này vì mắt/lông mày phải gán lại theo toạ độ.
_FACE_LAYOUT: tuple[tuple[int, str, str], ...] = (
    # longmaytrai 0-4, chạy từ ngoài vào trong
    (0, "longmaytrai", FRAME_LEFT),
    (1, "longmaytrai", FRAME_LEFT),
    (2, "longmaytrai", FRAME_LEFT),
    (3, "longmaytrai", FRAME_LEFT),
    (4, "longmaytrai", FRAME_LEFT),
    # longmayphai 5-9, chạy từ trong ra ngoài
    (5, "longmayphai", FRAME_RIGHT),
    (6, "longmayphai", FRAME_RIGHT),
    (7, "longmayphai", FRAME_RIGHT),
    (8, "longmayphai", FRAME_RIGHT),
    (9, "longmayphai", FRAME_RIGHT),
    # songmui 10-13
    (10, "songmui", FRAME_CENTER),
    (11, "songmui", FRAME_CENTER),
    (12, "songmui", FRAME_CENTER),
    (13, "songmui", FRAME_CENTER),
    # mattrai 14-21 và matphai 22-29 (index MediaPipe gán ở geometry)
    *((pid, "mattrai", FRAME_LEFT) for pid in range(14, 22)),
    *((pid, "matphai", FRAME_RIGHT) for pid in range(22, 30)),
    # moingoai 30-41 (kín)
    *((pid, "moingoai", FRAME_LEFT if i < 6 else FRAME_RIGHT) for i, pid in enumerate(range(30, 42))),
    # moitrong 42-49 (kín)
    *((pid, "moitrong", FRAME_LEFT if i < 4 else FRAME_RIGHT) for i, pid in enumerate(range(42, 50))),
)

FACE_POINTS: tuple[PointSpec, ...] = tuple(
    PointSpec(pid, str(pid), group, side) for pid, group, side in _FACE_LAYOUT
)

FACE_POINT_BY_ID: dict[int, PointSpec] = {p.point_id: p for p in FACE_POINTS}
POSE17_POINT_BY_ID: dict[int, PointSpec] = {p.point_id: p for p in POSE17_POINTS}

# Guideline mục 2.2 — 7 skeleton, tên và thứ tự không được đổi.
FACE_SKELETONS: tuple[SkeletonSpec, ...] = (
    SkeletonSpec("longmaytrai", False, (0, 1, 2, 3, 4)),
    SkeletonSpec("longmayphai", False, (5, 6, 7, 8, 9)),
    SkeletonSpec("songmui", False, (10, 11, 12, 13)),
    SkeletonSpec("mattrai", True, tuple(range(14, 22))),
    SkeletonSpec("matphai", True, tuple(range(22, 30))),
    SkeletonSpec("moingoai", True, tuple(range(30, 42))),
    SkeletonSpec("moitrong", True, tuple(range(42, 50))),
)

#: Nhóm cần kiểm tra R/L theo khung hình ở bài mặt.
FACE_SIDE_GROUPS: tuple[tuple[str, str, int, int], ...] = (
    ("longmaytrai", "longmayphai", 0, 5),
    ("mattrai", "matphai", 14, 22),
    ("moingoai", "moingoai", 30, 36),
    ("moitrong", "moitrong", 42, 46),
)

FACE_POINT_COUNT = len(FACE_POINTS)
POSE17_POINT_COUNT = len(POSE17_POINTS)


# ==========================================================================
# tiện ích
# ==========================================================================
def face_edges(spec: SkeletonSpec) -> tuple[tuple[int, int], ...]:
    """Cạnh nối các point ID của một skeleton mặt; contour kín thì khép vòng."""
    ids = list(spec.point_ids)
    edges = list(zip(ids, ids[1:]))
    if spec.closed and len(ids) > 2:
        edges.append((ids[-1], ids[0]))
    return tuple(edges)


def pose17_edges() -> tuple[tuple[int, int], ...]:
    """Cạnh của skeleton person; ưu tiên `edges` khai báo, không thì suy theo nhóm."""
    if POSE17_SKELETON.edges:
        return POSE17_SKELETON.edges
    return tuple(zip(POSE17_SKELETON.point_ids, POSE17_SKELETON.point_ids[1:]))


def face_label_names() -> tuple[str, ...]:
    return tuple(spec.resolved_label() for spec in FACE_SKELETONS)


def face_skeleton_for_point(point_id: int) -> SkeletonSpec | None:
    for spec in FACE_SKELETONS:
        if point_id in spec.point_ids:
            return spec
    return None


def sublabel_name(point_id: int) -> str:
    """Sublabel luôn là chuỗi số, cho cả hai bài."""
    return str(point_id)


def all_face_mediapipe_indices() -> set[int]:
    """Toàn bộ index MediaPipe mà tầng geometry sẽ dùng cho bài mặt.

    Gồm hai vòng môi đầy đủ (20 điểm mỗi vòng), vì `pick_points_by_arc` chọn 12/8
    điểm từ cả vòng chứ không chỉ từ bộ index cuối cùng.
    """
    used: set[int] = set(MP_NOSE_RIDGE_CHAIN)
    used.update(MP_OUTER_LIP_UPPER)
    used.update(MP_OUTER_LIP_LOWER)
    used.update(MP_INNER_LIP_UPPER)
    used.update(MP_INNER_LIP_LOWER)
    for group in MP_BROW_ANATOMICAL + MP_EYE_ANATOMICAL:
        used.update(group)
    return used
