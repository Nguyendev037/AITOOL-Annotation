"""Chạy MediaPipe Tasks API (1.x) khi bản cài không còn `mediapipe.solutions`.

Vì sao cần cả hai đường
-----------------------
MediaPipe 1.x đã bỏ `mediapipe.solutions` và chuyển sang Tasks API. Tasks API cần
file model `.task`, mà bản cài pip không kèm sẵn. Bản 0.10.x thì nhúng model trong
wheel nhưng không có bản dựng cho Python mới.

Trước đây `mediapipe_pose.py` chỉ hỗ trợ `solutions`, nên trên máy cài 1.0.1 thì
**không ai chạy lại được để kiểm** — đúng nguyên nhân khiến 4 lỗi landmark (mày,
miệng, mũi, nối) tồn tại lâu mà không bị phát hiện. Module này bổ sung đường Tasks
để bản cài nào cũng chạy được.

Model được tải một lần rồi lưu đệm; có thể trỏ sẵn bằng biến môi trường
``BROWSER_AGENT_MEDIAPIPE_MODEL_DIR`` khi môi trường không có mạng.
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Any

#: Tên file model Tasks API.
FACE_MODEL_NAME = "face_landmarker.task"
POSE_MODEL_NAME = "pose_landmarker.task"

_MODEL_URLS = {
    FACE_MODEL_NAME: (
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/1/face_landmarker.task"
    ),
    POSE_MODEL_NAME: (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
    ),
}

_CACHE_DIR = Path(
    os.environ.get("BROWSER_AGENT_MEDIAPIPE_MODEL_DIR")
    or (Path.home() / ".cache" / "browser-agent" / "mediapipe")
)


class MediaPipeModelUnavailable(RuntimeError):
    """Không có file model và không tải được."""


def has_face_tasks() -> bool:
    """Bản mediapipe đang cài có Tasks API cho FaceLandmarker không?"""
    try:
        import mediapipe as mp
        from mediapipe.tasks.python import vision  # noqa: F401
    except Exception:
        return False
    return hasattr(mp, "tasks") and hasattr(vision, "FaceLandmarker")


def model_path(name: str) -> Path:
    """Đường dẫn file model, tải về đệm nếu chưa có."""
    target = _CACHE_DIR / name
    if target.is_file() and target.stat().st_size > 0:
        return target
    url = _MODEL_URLS.get(name)
    if url is None:
        raise MediaPipeModelUnavailable(f"không biết URL cho model {name!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310
            payload = response.read()
    except Exception as exc:
        raise MediaPipeModelUnavailable(
            f"không tải được {name} từ {url}: {exc}. Nếu máy không có mạng, hãy tải "
            f"thủ công rồi đặt vào {target} hoặc đặt "
            f"BROWSER_AGENT_MEDIAPIPE_MODEL_DIR trỏ tới thư mục chứa model."
        ) from exc
    target.write_bytes(payload)
    return target


class TasksRunner:
    """Bọc FaceLandmarker + PoseLandmarker của Tasks API, khởi tạo lười."""

    def __init__(self, *, enable_face: bool = True, enable_pose: bool = True) -> None:
        self.enable_face = enable_face
        self.enable_pose = enable_pose
        self._face: Any = None
        self._pose: Any = None

    def _face_landmarker(self) -> Any:
        if self._face is None:
            import mediapipe as mp
            from mediapipe.tasks.python import vision

            options = vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path(FACE_MODEL_NAME))),
                running_mode=vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.3,
            )
            self._face = vision.FaceLandmarker.create_from_options(options)
        return self._face

    def _pose_landmarker(self) -> Any:
        if self._pose is None:
            import mediapipe as mp
            from mediapipe.tasks.python import vision

            options = vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path(POSE_MODEL_NAME))),
                running_mode=vision.RunningMode.IMAGE,
                num_poses=1,
                min_pose_detection_confidence=0.3,
            )
            self._pose = vision.PoseLandmarker.create_from_options(options)
        return self._pose

    def close(self) -> None:
        for landmarker in (self._face, self._pose):
            if landmarker is not None and hasattr(landmarker, "close"):
                landmarker.close()
        self._face = None
        self._pose = None
