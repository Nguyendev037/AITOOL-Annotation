#!/usr/bin/env python
"""Worker browser-use: tự lái trình duyệt, CHẠY BẰNG PYTHON CỦA LÕI.

Vì sao tách: `browser_use` chỉ có trong venv lõi (`D:\\browser-agent-core\\venv`),
và yêu cầu kiến trúc là **LLM chỉ giao việc** — mọi thao tác chuột/phím/điều hướng
do browser-use tự làm, không phải từng lệnh CDP thủ công.

    python worker_browsent.py --task "mở job và báo có bao nhiêu skeleton" \
        --url-file urls.txt --out result.json

Kết quả JSON::

    {"ok": true, "result": "...", "steps": 7, "urls": [...], "files": [...], "errors": []}

Đổi nhà cung cấp LLM KHÔNG cần sửa file này — xem `PROVIDERS` và biến môi trường:

    BROWSER_USE_PROVIDER=deepseek   # deepseek|openai|anthropic|ollama|litellm|...
    BROWSER_USE_MODEL=deepseek-chat
    BROWSER_USE_BASE_URL=https://api.deepseek.com
    BROWSER_USE_API_KEY=sk-...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Console Windows mặc định là cp1252 và sẽ chết khi in kết quả tiếng Việt
# (đã gặp thật: UnicodeEncodeError với 'ả'). Ép UTF-8 trước mọi thứ khác.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover
            pass


# --------------------------------------------------------------------------- #
# nhà cung cấp LLM — thay được, không cần sửa logic agent
# --------------------------------------------------------------------------- #
def _deepseek_thinking_enabled() -> bool:
    """Có bật thinking mode cho DeepSeek không. Mặc định TẮT.

    Vì sao mặc định tắt — đo được, không phải suy đoán. `deepseek-flash` bật thinking
    mặc định ở phía server, và thinking mode **từ chối `tool_choice` ép buộc**:

        tools + tool_choice=auto              -> OK
        tools + tool_choice=required          -> 400 Thinking mode does not support this tool_choice
        tools + tool_choice={function: ...}   -> 400 như trên
        tools + ép buộc + thinking disabled   -> OK

    browser-use ép `tool_choice={'type': 'function', ...}` ở bước trả kết quả cuối
    (xem `llm/deepseek/chat.py` nhánh function-calling), nên **bắt buộc phải tắt
    thinking**, nếu không agent chạy được vài bước rồi chết ở bước "Result".

    Đặt `BROWSER_USE_THINKING=true` nếu bạn đổi sang model không bật thinking mặc định.
    """
    return os.environ.get("BROWSER_USE_THINKING", "").strip().lower() in {"1", "true", "yes", "on"}


def build_llm(*, provider: str, model: str, base_url: str, api_key: str, temperature: float):
    """Tạo đối tượng LLM cho browser-use theo tên provider.

    `litellm` là đường thoát hiểm: nó bao được hơn 100 nhà cung cấp, nên kể cả
    provider chưa có lớp riêng trong browser-use vẫn dùng được mà không phải sửa gì.
    """
    key = provider.strip().lower()

    if key == "deepseek":
        from browser_use.llm.deepseek.chat import ChatDeepSeek

        kwargs = {"model": model, "temperature": temperature, "thinking": _deepseek_thinking_enabled()}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return ChatDeepSeek(**kwargs)

    if key == "openai":
        from browser_use.llm.openai.chat import ChatOpenAI

        kwargs = {"model": model, "temperature": temperature}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOpenAI(**kwargs)

    if key == "anthropic":
        from browser_use.llm.anthropic.chat import ChatAnthropic

        # ChatAnthropic không nhận api_key trong __init__ (đọc từ ANTHROPIC_API_KEY).
        kwargs = {"model": model, "temperature": temperature}
        if base_url:
            kwargs["base_url"] = base_url
        return ChatAnthropic(**kwargs)

    if key == "google":
        from browser_use.llm.google.chat import ChatGoogle

        return ChatGoogle(model=model, temperature=temperature)

    if key == "groq":
        from browser_use.llm.groq.chat import ChatGroq

        kwargs = {"model": model, "temperature": temperature}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return ChatGroq(**kwargs)

    if key == "ollama":
        from browser_use.llm.ollama.chat import ChatOllama

        # ChatOllama KHÔNG có tham số `temperature` trực tiếp; nó nhận `ollama_options`.
        # Truyền thẳng temperature vào đây sẽ TypeError (đã gặp thật).
        kwargs = {"model": model}
        if base_url:
            kwargs["host"] = base_url
        if temperature:
            kwargs["ollama_options"] = {"temperature": temperature}
        return ChatOllama(**kwargs)

    if key == "openrouter":
        from browser_use.llm.openrouter.chat import ChatOpenRouter

        kwargs = {"model": model, "temperature": temperature}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOpenRouter(**kwargs)

    if key == "mistral":
        from browser_use.llm.mistral.chat import ChatMistral

        kwargs = {"model": model, "temperature": temperature}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return ChatMistral(**kwargs)

    if key == "litellm":
        from browser_use.llm.litellm.chat import ChatLiteLLM

        # Đường thoát hiểm: bao mọi nhà cung cấp mà browser-use chưa có lớp riêng.
        kwargs = {"model": model, "temperature": temperature}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["api_base"] = base_url
        return ChatLiteLLM(**kwargs)

    raise SystemExit(
        f"provider {provider!r} chưa có lớp riêng. Dùng `--provider litellm` với "
        f"`--model <tên model của litellm>` để bao mọi nhà cung cấp khác."
    )


def provider_settings(args) -> dict:
    """Gom cấu hình provider từ tham số dòng lệnh, fallback sang biến môi trường.

    Lưu ý về model DeepSeek: browser-use ép `tool_choice` ở bước trả kết quả, mà
    DeepSeek **từ chối `tool_choice` ép buộc khi thinking bật**. Chỉ những model mà
    lớp `ChatDeepSeek` chịu gửi `thinking: disabled` mới chạy được (nó chỉ gửi khi
    tên model chứa `deepseek-v4`). Vì vậy mặc định ở đây là `deepseek-v4-pro`, KHÔNG
    phải `deepseek-flash` — `deepseek-flash` bật thinking ở phía server và không có
    cách tắt từ phía client, nên agent sẽ chết ở bước "Result".
    """
    env = os.environ
    default_model = env.get("BROWSER_USE_MODEL") or env.get("BROWSER_USE_DEEPSEEK_MODEL") or "deepseek-v4-pro"
    return {
        "provider": args.provider or env.get("BROWSER_USE_PROVIDER") or "deepseek",
        "model": args.model or default_model,
        "base_url": args.base_url or env.get("BROWSER_USE_BASE_URL") or env.get("DEEPSEEK_BASE_URL") or "",
        "api_key": args.api_key or env.get("BROWSER_USE_API_KEY") or env.get("DEEPSEEK_API_KEY") or "",
        "temperature": args.temperature,
    }


# --------------------------------------------------------------------------- #
# chạy tác vụ
# --------------------------------------------------------------------------- #
def build_task(args) -> str:
    """Ghép mô tả tác vụ. URL được đưa vào đề bài để agent biết phải mở trang nào."""
    parts = [args.task.strip()]
    if args.url:
        parts.append("Các URL cần làm việc:\n" + "\n".join(f"- {u}" for u in args.url))
    if args.out_dir:
        parts.append(f"Nếu cần lưu ảnh chụp màn hình, lưu vào thư mục: {args.out_dir}")
    return "\n\n".join(parts)


async def run(args) -> dict:
    from browser_use import Agent
    from browser_use.browser.profile import BrowserProfile

    settings = provider_settings(args)
    llm = build_llm(**settings)
    print(
        f"provider={settings['provider']} model={settings['model']} "
        f"base_url={settings['base_url'] or '(mặc định)'}",
        file=sys.stderr,
    )

    profile_kwargs: dict = {
        "headless": args.headless,
        "keep_alive": False,
    }
    if args.cdp_url:
        # Gắn vào trình duyệt đang mở -> dùng được phiên đã đăng nhập sẵn.
        profile_kwargs["cdp_url"] = args.cdp_url
    if args.user_data_dir:
        profile_kwargs["user_data_dir"] = args.user_data_dir
    if args.executable_path:
        profile_kwargs["executable_path"] = args.executable_path
    if args.window_size:
        width, _, height = args.window_size.partition("x")
        profile_kwargs["window_size"] = {"width": int(width), "height": int(height)}
    if args.disable_security:
        profile_kwargs["disable_security"] = True

    profile = BrowserProfile(**profile_kwargs)
    agent = Agent(
        task=build_task(args),
        llm=llm,
        browser_profile=profile,
        use_vision=not args.no_vision,
        max_failures=args.max_failures,
    )

    history = await agent.run(max_steps=args.max_steps)

    # Lấy kết quả cuối. API của browser-use đổi giữa các bản nên thử nhiều đường.
    result_text = ""
    for attribute in ("final_result",):
        getter = getattr(history, attribute, None)
        if callable(getter):
            try:
                result_text = getter() or ""
                break
            except Exception:  # pragma: no cover - phụ thuộc bản browser-use
                pass
    if not result_text:
        try:
            result_text = history.history[-1].result[-1].extracted_content or ""
        except Exception:  # pragma: no cover
            result_text = ""

    errors: list[str] = []
    getter = getattr(history, "errors", None)
    if callable(getter):
        try:
            errors = [str(e) for e in (getter() or [])][:10]
        except Exception:  # pragma: no cover
            pass

    steps = 0
    try:
        steps = len(history.history)
    except Exception:  # pragma: no cover
        pass

    return {
        "ok": bool(result_text),
        "provider": settings["provider"],
        "model": settings["model"],
        "result": result_text,
        "steps": steps,
        "errors": errors,
        "urls": args.url or [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, help="mô tả việc cần làm, bằng ngôn ngữ tự nhiên")
    parser.add_argument("--url", action="append", default=[], help="URL cần làm việc (lặp lại được)")
    parser.add_argument("--out", default=None, help="ghi kết quả JSON ra file này")
    parser.add_argument("--out-dir", default=None, help="thư mục cho ảnh chụp agent tạo ra")
    parser.add_argument("--max-steps", type=int, default=25)
    parser.add_argument("--max-failures", type=int, default=3)
    parser.add_argument("--headless", action="store_true", help="chạy ẩn (không xem được)")
    parser.add_argument("--no-vision", action="store_true", help="tắt ảnh chụp gửi cho LLM")
    parser.add_argument("--cdp-url", default=None, help="gắn vào trình duyệt đang mở, ví dụ http://127.0.0.1:9222")
    parser.add_argument("--user-data-dir", default=None)
    parser.add_argument("--executable-path", default=None)
    parser.add_argument("--window-size", default="1600x1000")
    parser.add_argument("--disable-security", action="store_true")
    # provider
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()

    if args.out_dir:
        Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    try:
        payload = asyncio.run(run(args))
    except Exception as exc:  # noqa: BLE001 - báo lỗi thật cho người gọi
        payload = {
            "ok": False,
            "result": "",
            "steps": 0,
            "errors": [f"{type(exc).__name__}: {exc}"],
            "urls": args.url or [],
        }
        text = json.dumps(payload, ensure_ascii=False)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        print(text)
        print(f"LỖI: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    text = json.dumps(payload, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
