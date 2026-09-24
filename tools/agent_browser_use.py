#!/usr/bin/env python3
"""Giao việc cho browser-use tự lái trình duyệt — repo KHÔNG tự bấm gì.

    # Việc bằng ngôn ngữ tự nhiên, browser-use tự quyết từng bước
    python tools/agent_browser_use.py --task "Cho tôi biết job này có bao nhiêu skeleton" \
        --url "https://cvat.note.transformerlabs.ai/tasks/344/jobs/2214"

    # Đổi nhà cung cấp LLM — không cần sửa code
    python tools/agent_browser_use.py --task "..." --url "..." --provider openai --model gpt-4o
    python tools/agent_browser_use.py --task "..." --url "..." --provider ollama --model qwen2.5

    # Gắn vào Chrome đang mở để dùng phiên đã đăng nhập
    python tools/agent_browser_use.py --task "..." --url "..." --cdp-url http://127.0.0.1:9222

Khác biệt cốt lõi so với `tools/agent_browser.py`
------------------------------------------------
`agent_browser.py` là **điều khiển trực tiếp**: người gọi (LLM) quyết định từng
`Page.navigate`, từng đoạn JS. `agent_browser_use.py` chỉ **giao việc**: nó đưa mô tả
bằng lời cho browser-use, và browser-use tự lập kế hoạch, tự bấm, tự đọc trang, tự
trả kết quả. Repo không can thiệp vào từng bước.

Nhờ vậy đổi nhà cung cấp LLM không đụng tới logic lái trình duyệt: chỉ đổi tham số
`--provider/--model`, hoặc đặt biến môi trường `BROWSER_USE_PROVIDER/MODEL/API_KEY`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover
            pass

from browser_agent.config import browser_settings, load_env  # noqa: E402

WORKER = ROOT / "browser_agent" / "vision" / "worker_browsent.py"


def provider_env(args) -> dict[str, str]:
    """Biến môi trường cho worker. Đây là chỗ duy nhất quyết định provider."""
    env = dict(os.environ)
    mapping = {
        "BROWSER_USE_PROVIDER": args.provider,
        "BROWSER_USE_MODEL": args.model,
        "BROWSER_USE_BASE_URL": args.base_url,
        "BROWSER_USE_API_KEY": args.api_key,
    }
    for key, value in mapping.items():
        if value:
            env[key] = value
    return env


def main() -> int:
    load_env()
    settings = browser_settings()

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--task", required=True, help="việc cần làm, bằng ngôn ngữ tự nhiên")
    parser.add_argument("--url", action="append", default=[], help="URL cần làm việc (lặp lại được)")
    parser.add_argument("--max-steps", type=int, default=25)
    parser.add_argument("--headless", action="store_true", help="chạy ẩn, không xem được")
    parser.add_argument("--no-vision", action="store_true", help="tắt ảnh chụp gửi cho LLM")
    parser.add_argument("--cdp-url", default=None, help="gắn vào trình duyệt đang mở")
    parser.add_argument("--out", default=None, help="ghi kết quả JSON ra file")
    parser.add_argument("--json", action="store_true", help="in cả JSON thô")
    # provider — không có thì lấy từ .env / biến môi trường
    parser.add_argument("--provider", default=None, help="deepseek|openai|anthropic|google|ollama|litellm|...")
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    python = settings.python
    if not python.is_file():
        print(
            f"Không thấy python của lõi tại {python}.\n"
            "browser-use chỉ có trong venv lõi; đặt BROWSER_CORE_DIR trong .env.",
            file=sys.stderr,
        )
        return 2
    if not WORKER.is_file():
        print(f"Không thấy worker {WORKER}", file=sys.stderr)
        return 2

    command = [
        str(python),
        str(WORKER),
        "--task",
        args.task,
        "--max-steps",
        str(args.max_steps),
    ]
    for url in args.url:
        command += ["--url", url]
    if args.headless:
        command.append("--headless")
    if args.no_vision:
        command.append("--no-vision")
    if args.cdp_url:
        command += ["--cdp-url", args.cdp_url]

    out_path = Path(args.out).resolve() if args.out else ROOT / "work" / "browser_use_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    command += ["--out", str(out_path), "--out-dir", str(ROOT / "work" / "browser_use_shots")]

    print("giao việc cho browser-use (agent tự lái, không can thiệp từng bước)...")
    print(f"  việc : {args.task[:110]}")
    for url in args.url:
        print(f"  url  : {url}")
    print(f"  model: {args.model or os.environ.get('BROWSER_USE_MODEL') or 'deepseek-v4-pro (mặc định)'}")

    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=provider_env(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if not out_path.is_file():
        print("worker không tạo kết quả. stderr cuối:", file=sys.stderr)
        print((completed.stderr or "")[-1500:], file=sys.stderr)
        return 1

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    print(f"\nkết quả (ok={payload.get('ok')}, {payload.get('steps')} bước):")
    print(payload.get("result") or "(không có nội dung)")
    errors = [e for e in (payload.get("errors") or []) if e and e != "None"]
    for error in errors[:5]:
        print(f"  lỗi: {error}", file=sys.stderr)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out:
        print(f"\nđã ghi {out_path}")

    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
