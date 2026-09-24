"""Cấu hình dùng chung cho browser-agent.

Đọc `.env` ở gốc repo (không ghi đè biến môi trường đã có), rồi phơi ra các
dataclass nhỏ. Không import gì nặng ở đây: module này phải import được cả trong
venv chung trên ổ D lẫn python hệ thống.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Nạp `.env` kiểu KEY=VALUE. Bỏ qua comment và dòng trống."""
    path = path or ROOT / ".env"
    loaded: dict[str, str] = {}
    if not path.is_file():
        return loaded
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        loaded[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return loaded


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


@dataclass(frozen=True)
class CvatSettings:
    """Kết nối tới một CVAT instance (online hoặc localhost)."""

    url: str
    token: str
    label: str = "cvat"

    @property
    def api(self) -> str:
        return self.url.rstrip("/") + "/api"

    @property
    def configured(self) -> bool:
        return bool(self.url and self.token)

    def describe(self) -> str:
        return f"{self.label}: {self.url or '(chưa cấu hình)'} token={'có' if self.token else 'THIẾU'}"


@dataclass(frozen=True)
class VisionSettings:
    """Nguồn thị giác cho agent."""

    model_service_url: str
    prefer: str  # local | service
    facemesh: bool
    auto_rotate: bool
    min_visibility: float


@dataclass(frozen=True)
class BrowserSettings:
    """Nơi lõi browser-use sống và cách nó mở trình duyệt."""

    core_dir: Path
    cdp_url: str
    headless: bool
    llm_model: str
    llm_base_url: str
    llm_api_key: str

    @property
    def python(self) -> Path:
        return self.core_dir / "venv" / "Scripts" / "python.exe"

    @property
    def installed(self) -> bool:
        return self.python.is_file()


def cvat_settings() -> dict[str, CvatSettings]:
    """Cả hai CVAT instance đã biết: `online` và `local`."""
    return {
        "online": CvatSettings(
            url=_env("CVAT_URL", default="https://cvat.note.transformerlabs.ai"),
            token=_env("CVAT_TOKEN"),
            label="CVAT online",
        ),
        "local": CvatSettings(
            url=_env("CVAT_LOCAL_URL", default="http://localhost:8080"),
            token=_env("CVAT_LOCAL_TOKEN"),
            label="CVAT localhost",
        ),
    }


def resolve_cvat(target: str | None = None) -> CvatSettings:
    """Chọn instance: theo tên, hoặc tự chọn cái nào có token."""
    instances = cvat_settings()
    if target:
        key = target.strip().lower()
        if key not in instances:
            raise KeyError(f"không biết CVAT target {target!r}; có: {', '.join(instances)}")
        return instances[key]
    for name in ("online", "local"):
        if instances[name].configured:
            return instances[name]
    return instances["online"]


def vision_settings() -> VisionSettings:
    return VisionSettings(
        model_service_url=_env("SAM_URL", default="http://127.0.0.1:8001").rstrip("/"),
        prefer=_env("AGENT_VISION_PREFER", default="local").strip().lower(),
        facemesh=_env("AGENT_FACEMESH", default="true").strip().lower() in {"1", "true", "yes", "on"},
        auto_rotate=_env("AGENT_AUTO_ROTATE", default="true").strip().lower() in {"1", "true", "yes", "on"},
        min_visibility=float(_env("AGENT_MIN_VISIBILITY", default="0.35")),
    )


def browser_settings() -> BrowserSettings:
    return BrowserSettings(
        core_dir=Path(_env("BROWSER_CORE_DIR", default=r"D:\browser-agent-core")),
        cdp_url=_env("BROWSER_CDP_URL", default="http://127.0.0.1:9222").rstrip("/"),
        headless=_env("BROWSER_HEADLESS", default="false").strip().lower() in {"1", "true", "yes", "on"},
        llm_model=_env("DEEPSEEK_MODEL", default="deepseek-flash"),
        llm_base_url=_env("DEEPSEEK_BASE_URL", default="https://api.deepseek.com").rstrip("/"),
        llm_api_key=_env("DEEPSEEK_API_KEY"),
    )


load_env()
