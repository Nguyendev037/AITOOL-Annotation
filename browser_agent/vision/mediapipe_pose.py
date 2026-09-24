"""Suy luận landmark bằng MediaPipe, hỗ trợ CẢ HAI API.

MediaPipe 0.10.x nhúng sẵn model và dùng ``mediapipe.solutions``; MediaPipe 1.x đã
bỏ API đó và chuyển sang Tasks API (cần file ``.task``). Module này tự chọn đường
chạy được, để bản cài nào cũng suy luận được.

Vì sao điều này quan trọng: bản trước chỉ hỗ trợ ``solutions``. Trên máy cài
MediaPipe 1.0.1, mọi lệnh suy luận face đều ném lỗi — nghĩa là **không ai chạy lại
được để kiểm**, và đó là lý do bốn lỗi landmark (mày/miệng/mũi/đường nối) tồn tại
lâu mà không bị phát hiện.

Module này không tự tải ảnh; nó nhận ``numpy.ndarray`` RGB.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from ..geometry import MP_EYE_ANATOMICAL, MP_BROW_ANATOMICAL


class MediaPipeUnavailable(RuntimeError):
    """MediaPipe chưa cài, hoặc bản cài không dùng được API nào."""


@dataclass
class RawLandmark:
    """Một landmark thô, toạ độ đã chuẩn hoá 0..1 theo ảnh."""

    index: int
    x: float
    y: float
    z: float = 0.0
    visibility: float = 1.0
    presence: float = 1.0

    @property
    def xy(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass
class PoseObservation:
    landmarks: list[RawLandmark] = field(default_factory=list)
    rotation_applied: int = 0

    @property
    def ok(self) -> bool:
        return len(self.landmarks) >= 29


@dataclass
class FaceObservation:
    landmarks: list[RawLandmark] = field(default_factory=list)
    rotation_applied: int = 0

    @property
    def ok(self) -> bool:
        return len(self.landmarks) >= 468


def mediapipe_solutions() -> Any:
    """Trả về module ``mediapipe.solutions``, hoặc ném lỗi rõ ràng."""
    try:
        import mediapipe as mp
    except ModuleNotFoundError as exc:  # pragma: no cover - phụ thuộc môi trường
        raise MediaPipeUnavailable(
            "Chưa cài mediapipe. Cài bằng: python -m pip install mediapipe"
        ) from exc
    solutions = getattr(mp, "solutions", None)
    if solutions is None:
        raise MediaPipeUnavailable(
            f"mediapipe {getattr(mp, '__version__', '?')} không còn API `solutions`. "
            "Đường Tasks API sẽ được dùng thay thế."
        )
    return solutions


class MediaPipeRunner:
    """Bọc Pose + FaceMesh, tự chọn API, khởi tạo lười và chỉ một lần.

    ``static_image_mode=True`` là cố ý: bài này annotate từng ảnh rời, không phải
    video, nên không muốn FaceMesh "nhớ" khuôn mặt của ảnh trước.
    """

    def __init__(self, *, enable_face: bool = True) -> None:
        self.enable_face = enable_face
        self._lock = threading.Lock()
        self._pose: Any = None
        self._face: Any = None
        self._tasks: Any = None
        self._api: str | None = None

    # -- chọn API ---------------------------------------------------------- #
    def _resolve_api(self) -> str:
        """``"solutions"`` nếu bản cài còn API cũ, ngược lại ``"tasks"``."""
        if self._api is not None:
            return self._api
        try:
            mediapipe_solutions()
            self._api = "solutions"
        except MediaPipeUnavailable as exc:
            if "Chưa cài mediapipe" in str(exc):
                raise
            from .mediapipe_tasks import has_face_tasks

            if has_face_tasks():
                self._api = "tasks"
            else:
                raise MediaPipeUnavailable(
                    f"{exc} Và bản cài cũng không có Tasks API dùng được."
                ) from exc
        return self._api

    @property
    def api(self) -> str:
        """API đang dùng: ``"solutions"`` hoặc ``"tasks"`` (dò lúc gọi lần đầu)."""
        return self._resolve_api()

    def _tasks_runner(self) -> Any:
        if self._tasks is None:
            from .mediapipe_tasks import TasksRunner

            self._tasks = TasksRunner(enable_face=self.enable_face)
        return self._tasks

    # -- khởi tạo lười ---------------------------------------------------- #
    def _pose_solution(self) -> Any:
        if self._pose is None:
            solutions = mediapipe_solutions()
            self._pose = solutions.pose.Pose(
                static_image_mode=True,
                model_complexity=1,
                enable_segmentation=False,
                min_detection_confidence=0.3,
            )
        return self._pose

    def _face_solution(self) -> Any:
        if self._face is None:
            solutions = mediapipe_solutions()
            self._face = solutions.face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=0.3,
            )
        return self._face

    # -- suy luận --------------------------------------------------------- #
    def detect_pose(self, rgb: Any) -> PoseObservation:
        if self._resolve_api() == "tasks":
            return self._detect_pose_tasks(rgb)
        with self._lock:
            result = self._pose_solution().process(rgb)
        if not getattr(result, "pose_landmarks", None):
            return PoseObservation()
        landmarks = [
            RawLandmark(i, lm.x, lm.y, getattr(lm, "z", 0.0), getattr(lm, "visibility", 1.0))
            for i, lm in enumerate(result.pose_landmarks.landmark)
        ]
        return PoseObservation(landmarks=landmarks)

    def _detect_pose_tasks(self, rgb: Any) -> PoseObservation:
        import numpy as np

        with self._lock:
            result = self._tasks_runner()._pose_landmarker().detect(
                _to_mp_image(rgb, np)
            )
        if not result.pose_landmarks:
            return PoseObservation()
        landmarks = [
            RawLandmark(
                i,
                float(lm.x),
                float(lm.y),
                float(getattr(lm, "z", 0.0) or 0.0),
                float(getattr(lm, "visibility", 1.0) or 1.0),
                float(getattr(lm, "presence", 1.0) or 1.0),
            )
            for i, lm in enumerate(result.pose_landmarks[0])
        ]
        return PoseObservation(landmarks=landmarks)

    def detect_face(self, rgb: Any) -> FaceObservation:
        if not self.enable_face:
            return FaceObservation()
        if self._resolve_api() == "tasks":
            return self._detect_face_tasks(rgb)
        with self._lock:
            result = self._face_solution().process(rgb)
        multi = getattr(result, "multi_face_landmarks", None)
        if not multi:
            return FaceObservation()
        # max_num_faces=1 nên chỉ có một khuôn mặt; lấy cái đầu tiên.
        landmarks = [
            RawLandmark(i, lm.x, lm.y, getattr(lm, "z", 0.0), 1.0)
            for i, lm in enumerate(multi[0].landmark)
        ]
        return FaceObservation(landmarks=landmarks)

    def _detect_face_tasks(self, rgb: Any) -> FaceObservation:
        import numpy as np

        # Tasks API 1.x trả 478 điểm khi model có iris; bài này chỉ dùng 468 điểm
        # đầu (mesh gốc) nên cắt bớt để các index không đổi nghĩa.
        with self._lock:
            result = self._tasks_runner()._face_landmarker().detect(_to_mp_image(rgb, np))
        if not result.face_landmarks:
            return FaceObservation()
        landmarks = [
            RawLandmark(i, float(lm.x), float(lm.y), float(getattr(lm, "z", 0.0) or 0.0), 1.0)
            for i, lm in enumerate(result.face_landmarks[0][:468])
        ]
        return FaceObservation(landmarks=landmarks)

    def close(self) -> None:
        for solution in (self._pose, self._face):
            if solution is not None and hasattr(solution, "close"):
                solution.close()
        if self._tasks is not None:
            self._tasks.close()
        self._pose = None
        self._face = None
        self._tasks = None


def _to_mp_image(rgb: Any, np: Any) -> Any:
    """Đổi ndarray RGB sang ``mp.Image`` của Tasks API."""
    import mediapipe as mp

    array = np.asarray(rgb)
    if array.dtype != np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=array)


def anatomical_eye_sets() -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Hai bộ contour mắt theo giải phẫu, dùng cho việc tự gán trái/phải."""
    return MP_EYE_ANATOMICAL


def anatomical_brow_sets() -> tuple[tuple[int, ...], tuple[int, ...]]:
    return MP_BROW_ANATOMICAL
