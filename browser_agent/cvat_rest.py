"""Client REST cho CVAT — đường thực thi không dùng trình duyệt.

Vì sao vẫn cần đường này dù đã có browser-agent: nó là **đối chứng**. Khi
browser-agent bấm sai hoặc đọc sai trạng thái, REST cho biết trạng thái thật của
job. Nó cũng là đường duy nhất kiểm chứng được tự động trong CI.

Ba chế độ ghi, cố ý đặt tên theo hậu quả:

- ``append``  — chỉ tạo shape mới, **không** đụng dữ liệu đang có.
- ``update``  — sửa shape đã có theo id, **không** tạo và **không** xoá.
- ``replace`` — ghi đè toàn bộ annotation. Đây đúng là thao tác mà cả hai
  guideline cấm ("Không tự nạp annotation lên task … ghi đè toàn bộ dữ liệu đang
  có"), nên nó **không** phải mặc định và phải bật tường minh.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import CvatSettings

DEFAULT_TIMEOUT = 60.0

#: CVAT API v2 bắt buộc client khai báo version qua Accept; gửi
#: `application/json` trần sẽ bị trả 406 "Could not satisfy the request Accept
#: header." Đây là yêu cầu content negotiation của drf-versioning trong CVAT.
ACCEPT_V2 = "application/vnd.cvat+json"
ACCEPT_JSON = "application/json"

WRITE_APPEND = "append"
WRITE_UPDATE = "update"
WRITE_REPLACE = "replace"
WRITE_MODES = (WRITE_APPEND, WRITE_UPDATE, WRITE_REPLACE)


class CvatError(RuntimeError):
    """Lỗi trả về từ CVAT, giữ nguyên body để đọc được thông báo thật."""

    def __init__(self, status: int, url: str, body: str) -> None:
        super().__init__(f"HTTP {status} {url}: {body[:400]}")
        self.status = status
        self.url = url
        self.body = body


@dataclass
class CvatShape:
    """Một shape đọc từ CVAT (đã rút gọn về thứ agent cần)."""

    id: int | None
    label_id: int
    type: str
    frame: int
    points: list[float] = field(default_factory=list)
    occluded: bool = False
    outside: bool = False
    attributes: list[dict] = field(default_factory=list)
    elements: list["CvatShape"] = field(default_factory=list)
    source: str = ""
    group_id: int | None = None

    @property
    def is_skeleton(self) -> bool:
        return self.type == "skeleton"

    def summary(self) -> str:
        if self.is_skeleton:
            visible = sum(1 for e in self.elements if not e.outside and not e.occluded)
            outside = sum(1 for e in self.elements if e.outside)
            occluded = sum(1 for e in self.elements if e.occluded and not e.outside)
            return (
                f"skeleton#{self.id} label={self.label_id} frame={self.frame} "
                f"elements={len(self.elements)} visible={visible} occluded={occluded} outside={outside}"
            )
        if self.type == "points":
            return f"points#{self.id} label={self.label_id} frame={self.frame} points={len(self.points) // 2}"
        return f"{self.type}#{self.id} label={self.label_id} frame={self.frame}"


class CvatClient:
    """Client tối giản, chỉ dùng thư viện chuẩn (không cần cvat-sdk)."""

    def __init__(self, settings: CvatSettings, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.settings = settings
        self.timeout = timeout

    # -- HTTP ------------------------------------------------------------- #
    def _headers(self, extra: dict[str, str] | None = None, *, accept: str = ACCEPT_V2) -> dict[str, str]:
        headers = {"Accept": accept}
        if self.settings.token:
            headers["Authorization"] = f"Token {self.settings.token}"
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: Any = None,
        raw: bool = False,
        accept: str = ACCEPT_V2,
    ) -> Any:
        url = self.settings.api + path
        if params:
            url += "?" + urlencode(params)
        body = None
        headers = self._headers(accept=accept)
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = ACCEPT_JSON

        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read()
        except HTTPError as exc:
            raise CvatError(exc.code, url, exc.read().decode("utf-8", "replace")) from exc
        except URLError as exc:
            raise CvatError(0, url, f"không kết nối được: {exc.reason}") from exc

        if raw:
            return data
        if not data:
            return None
        return json.loads(data.decode("utf-8"))

    # -- tạo task kèm ảnh ------------------------------------------------- #
    def upload_task_data(
        self,
        task_id: int,
        *,
        files: list[Path] | None = None,
        header: dict[str, str] | None = None,
        fields: dict[str, str] | None = None,
        field_name: str = "client_files[0]",
    ) -> Any:
        """Một pha của luồng nạp dữ liệu task (start / gửi file / finish).

        Đã kiểm chứng trên CVAT 2.74. Multipart nên KHÔNG được tái sử dụng
        ``upload_annotations``: endpoint và ý nghĩa header khác nhau.
        """
        boundary = "browseragenttaskdata"
        parts: list[bytes] = []

        def text_field(name: str, value: str) -> None:
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
            )

        for name, value in (fields or {}).items():
            text_field(name, value)

        for path in files or []:
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{path.name}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n".encode()
            )
            parts.append(path.read_bytes())
            parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())

        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        headers.update(header or {})
        request = Request(
            f"{self.settings.api}/tasks/{task_id}/data/",
            data=b"".join(parts),
            headers=self._headers(headers, accept=ACCEPT_V2),
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8") or "null"
        except HTTPError as exc:
            raise CvatError(exc.code, request.full_url, exc.read().decode("utf-8", "replace")) from exc
        except URLError as exc:
            raise CvatError(0, request.full_url, f"không kết nối được: {exc.reason}") from exc
        return json.loads(raw)

    def create_task_with_images(
        self,
        *,
        name: str,
        images: list[Path],
        project_id: int | None = None,
        image_quality: int = 70,
        wait_seconds: float = 90.0,
        poll_interval: float = 2.0,
    ) -> tuple[int, int]:
        """Tạo task kèm ảnh, chờ xong, trả ``(task_id, job_id)``.

        Ba cái bẫy của CVAT 2.74, đều đã trả giá thật:

        1. ``POST /api/tasks`` **chỉ nhận JSON** (schema OpenAPI khai đúng vậy);
           gửi multipart sẽ bị 415.
        2. Task phải khai trước ``client_files`` (tên file), nếu không worker chết
           với ``ValueError: No media data found`` và task ở lại ``size=0``.
        3. Pha ``Upload-Finish`` phải gửi kèm ``image_quality``, nếu không worker
           chết với ``The 'image_quality' parameter is required...``.
        """
        if not images:
            raise ValueError("cần ít nhất một ảnh")

        payload: dict[str, Any] = {
            "name": name,
            "image_quality": image_quality,
            "client_files": [f"client_files[0]/{path.name}" for path in images],
        }
        if project_id is not None:
            payload["project_id"] = project_id
        created = self.request("POST", "/tasks", payload=payload)
        task_id = int(created["id"])

        self.upload_task_data(task_id, header={"Upload-Start": "true"})
        self.upload_task_data(task_id, files=images)
        self.upload_task_data(
            task_id,
            header={"Upload-Finish": "true"},
            fields={"image_quality": str(image_quality)},
        )

        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            jobs = self.request("GET", "/jobs", params={"task_id": task_id, "page_size": 1})
            if jobs.get("count"):
                return task_id, int(jobs["results"][0]["id"])
            state = self.task(task_id).get("status")
            if state in ("failed", "error"):
                raise CvatError(0, f"/tasks/{task_id}", f"nạp ảnh thất bại: status={state}")
            time.sleep(poll_interval)
        raise CvatError(0, f"/tasks/{task_id}", "hết thời gian chờ task có job")

    # -- đọc -------------------------------------------------------------- #
    def server_about(self) -> dict:
        return self.request("GET", "/server/about")

    def user_self(self) -> dict:
        return self.request("GET", "/users/self")

    def job(self, job_id: int) -> dict:
        return self.request("GET", f"/jobs/{job_id}")

    def task(self, task_id: int) -> dict:
        return self.request("GET", f"/tasks/{task_id}")

    def job_labels(self, job_id: int) -> list[dict]:
        """Label cấp project/task của job, kèm sublabel của skeleton."""
        data = self.request("GET", "/labels", params={"job_id": job_id})
        results = data.get("results", data) if isinstance(data, dict) else data
        return list(results)

    def annotations(self, job_id: int) -> dict:
        return self.request("GET", f"/jobs/{job_id}/annotations")

    def shapes(self, job_id: int) -> list[CvatShape]:
        data = self.annotations(job_id)
        return [shape_from_api(item) for item in data.get("shapes", [])]

    def frame_bytes(self, job_id: int, frame: int, *, quality: str = "original") -> bytes:
        """Tải ảnh của một frame. Dùng cho vision khi không có ảnh local."""
        return self.request(
            "GET",
            f"/jobs/{job_id}/data",
            params={"type": "frame", "number": frame, "quality": quality},
            raw=True,
        )

    # -- ghi -------------------------------------------------------------- #
    def patch_annotations(
        self,
        job_id: int,
        *,
        action: str,
        shapes: list[dict] | None = None,
        tracks: list[dict] | None = None,
        tags: list[dict] | None = None,
    ) -> dict:
        """Ghi annotation. ``action`` là **query param**, không phải field trong body.

        CVAT 2.74 (OpenAPI: ``/api/jobs/{id}/annotations/`` PATCH) khai ``action``
        là parameter ``in: query`` bắt buộc; body chỉ chứa ``shapes/tracks/tags``
        theo ``PatchedLabeledDataRequest``. Gửi ``{"action": ...}`` trong body sẽ
        bị trả 400 ``Please specify a correct 'action' for the request``.
        """
        payload: dict[str, Any] = {}
        if shapes is not None:
            payload["shapes"] = shapes
        if tracks is not None:
            payload["tracks"] = tracks
        if tags is not None:
            payload["tags"] = tags
        return self.request(
            "PATCH", f"/jobs/{job_id}/annotations", params={"action": action}, payload=payload
        )

    def create_shapes(self, job_id: int, shapes: list[dict]) -> dict:
        """Chế độ ``append``: chỉ thêm, không đụng dữ liệu đang có."""
        return self.patch_annotations(job_id, action="create", shapes=shapes)

    def update_shapes(self, job_id: int, shapes: list[dict]) -> dict:
        """Chế độ ``update``: sửa theo id đã có."""
        return self.patch_annotations(job_id, action="update", shapes=shapes)

    def replace_shapes(self, job_id: int, shapes: list[dict]) -> dict:
        """Chế độ ``replace``: GHI ĐÈ toàn bộ annotation của job.

        Cố ý tách khỏi ``create``/``update`` và phải gọi tường minh, vì đây đúng
        là thao tác mà cả hai guideline cấm ("Không tự nạp annotation lên task …
        ghi đè toàn bộ dữ liệu đang có"). Không có đường nào trong package này tự
        động rơi vào chế độ này.

        CVAT không có một action "replace" duy nhất, nên làm đúng hai bước
        xoá-hết-rồi-tạo-lại. Nếu bước tạo lỗi, job sẽ ở trạng thái trống — vì vậy
        hàm này chỉ được gọi khi người dùng đã xác nhận.
        """
        existing = [shape.id for shape in self.shapes(job_id) if shape.id is not None]
        if existing:
            self.delete_shapes(job_id, existing)
        return self.patch_annotations(job_id, action="create", shapes=shapes)

    def delete_shapes(self, job_id: int, shape_ids: list[int]) -> dict:
        return self.patch_annotations(
            job_id, action="delete", shapes=[{"id": sid} for sid in shape_ids]
        )

    # -- tiện ích --------------------------------------------------------- #
    def smoke(self) -> dict:
        """Kiểm tra kết nối, trả về thông tin để in ra CLI."""
        about = self.server_about()
        me = self.user_self()
        return {
            "url": self.settings.url,
            "version": about.get("version"),
            "user": me.get("username"),
            "is_superuser": me.get("is_superuser"),
        }

    def download_annotations(self, job_id: int, fmt: str = "CVAT for images 1.1") -> bytes:
        return self.request(
            "GET",
            f"/jobs/{job_id}/annotations",
            params={"format": fmt, "action": "download"},
            raw=True,
        )

    def upload_annotations(self, job_id: int, path: Path, fmt: str = "CVAT for images 1.1") -> Any:
        """Nạp file annotation. Đây là thao tác GHI ĐÈ — guideline cấm tự làm."""
        # RFC 2046: dấu phân cách trong body là "--" + boundary, nên boundary
        # KHÔNG được bắt đầu bằng "--". Bản cũ dùng boundary "----browseragent..."
        # và ghi "--{boundary}" -> body có 6 gạch còn header khai 4, CVAT trả 415
        # Unsupported media type.
        boundary = "browseragentboundary"
        content = path.read_bytes()
        body = b"".join(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="annotation_file"; filename="{path.name}"\r\n'.encode(),
                b"Content-Type: application/octet-stream\r\n\r\n",
                content,
                f"\r\n--{boundary}--\r\n".encode(),
            ]
        )
        url = (
            self.settings.api
            + f"/jobs/{job_id}/annotations?{urlencode({'format': fmt, 'action': 'upload'})}"
        )
        request = Request(
            url,
            data=body,
            headers=self._headers(
                {"Content-Type": f"multipart/form-data; boundary={boundary}"}, accept=ACCEPT_V2
            ),
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8") or "null")
        except HTTPError as exc:
            raise CvatError(exc.code, url, exc.read().decode("utf-8", "replace")) from exc
        except URLError as exc:
            raise CvatError(0, url, f"không kết nối được: {exc.reason}") from exc


def shape_from_api(item: dict) -> CvatShape:
    return CvatShape(
        id=item.get("id"),
        label_id=item.get("label_id"),
        type=item.get("type", ""),
        frame=item.get("frame", 0),
        points=list(item.get("points") or []),
        occluded=bool(item.get("occluded")),
        outside=bool(item.get("outside")),
        attributes=list(item.get("attributes") or []),
        elements=[shape_from_api(child) for child in (item.get("elements") or [])],
        source=item.get("source", ""),
        group_id=item.get("group"),
    )


def find_label_by_name(labels: list[dict], name: str) -> dict | None:
    wanted = name.strip().lower()
    for label in labels:
        if str(label.get("name", "")).strip().lower() == wanted:
            return label
    return None


def sublabel_map(label: dict) -> dict[str, int]:
    """``{tên sublabel: label_id}`` của một label skeleton."""
    result: dict[str, int] = {}
    for child in label.get("sublabels", []) or []:
        result[str(child.get("name", ""))] = int(child.get("id"))
    return result
