"""Test cho lớp giao việc browser-use.

Vì sao test bằng cách đọc mã thay vì import: `browser_use` chỉ có trong venv lõi, còn
`pytest` chạy bằng python hệ thống (không cài được gì từ PyPI). Nên không thể import
`worker_browsent` để test trực tiếp. Nhưng thứ cần khoá lại — **danh sách provider và
hợp đồng CLI** — kiểm tra được bằng AST và đọc văn bản.

Đây không phải test hình thức: nếu ai đó xoá một nhánh provider, hoặc để provider
không xác định rơi vào một lớp cứng, tính "thay LLM linh hoạt" mất đi mà không ai biết.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "browser_agent" / "vision" / "worker_browsent.py"
DELEGATOR = ROOT / "tools" / "agent_browser_use.py"

#: Provider mà browser-use 0.13 có lớp riêng và worker phải phục vụ được.
EXPECTED_PROVIDERS = {
    "deepseek",
    "openai",
    "anthropic",
    "google",
    "groq",
    "ollama",
    "openrouter",
    "mistral",
    "litellm",
}


def _build_llm_source() -> str:
    tree = ast.parse(WORKER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "build_llm":
            return ast.get_source_segment(WORKER.read_text(encoding="utf-8"), node) or ""
    raise AssertionError("không thấy hàm build_llm trong worker")


def test_worker_file_exists_and_is_runnable_by_core_python():
    assert WORKER.is_file(), "worker browser-use phải nằm trong repo"
    source = WORKER.read_text(encoding="utf-8")
    # Phải tự đổi encoding, nếu không console Windows chết khi in tiếng Việt.
    assert "reconfigure(encoding=\"utf-8\"" in source


def test_every_expected_provider_has_a_branch():
    source = _build_llm_source()
    missing = [p for p in EXPECTED_PROVIDERS if f'"{p}"' not in source]
    assert not missing, f"provider thiếu nhánh trong build_llm: {sorted(missing)}"


def test_litellm_escape_hatch_is_present_and_documented():
    """Không có lớp riêng thì phải còn đường litellm, nếu không hết linh hoạt."""
    source = _build_llm_source()
    assert "litellm" in source
    assert "api_base" in source, "ChatLiteLLM nhận api_base, không phải base_url"


def test_unknown_provider_fails_loudly_not_silently_defaulted():
    source = _build_llm_source()
    assert "raise SystemExit" in source, "provider lạ phải báo lỗi rõ, không im lặng"


def test_ollama_does_not_receive_temperature_directly():
    """ChatOllama không có tham số `temperature`; truyền thẳng sẽ TypeError.

    Đã gặp thật: build_llm ban đầu dùng chung `common` cho mọi provider và chết ở
    Ollama. Test này khoá lại rằng temperature phải đi qua `ollama_options`.
    """
    source = _build_llm_source()
    marker = 'if key == "ollama":'
    assert marker in source
    ollama_branch = source.split(marker, 1)[1].split("if key ==", 1)[0]
    assert "ollama_options" in ollama_branch
    assert 'model=model, temperature=temperature' not in ollama_branch


def test_deepseek_default_model_is_the_one_that_accepts_forced_tool_choice():
    """Model mặc định phải là model chạy được với browser-use.

    DeepSeek từ chối `tool_choice` ép buộc khi thinking bật. `deepseek-flash` bật
    thinking ở phía server và lớp ChatDeepSeek **không gửi** extra_body cho nó (nó chỉ
    gửi khi tên model chứa `deepseek-v4`), nên dùng flash sẽ chết ở bước "Result".
    """
    source = WORKER.read_text(encoding="utf-8")
    assert '"deepseek-v4-pro"' in source, "mặc định phải là deepseek-v4-pro"
    provider_fn = source.split("def provider_settings", 1)[1].split("def ", 1)[0]
    assert 'env.get("DEEPSEEK_MODEL")' not in provider_fn, (
        "không được lấy thẳng DEEPSEEK_MODEL: .env đang đặt deepseek-flash và sẽ làm agent chết"
    )


def test_thinking_flag_is_documented_and_defaults_off():
    source = WORKER.read_text(encoding="utf-8")
    assert "BROWSER_USE_THINKING" in source
    assert "return os.environ.get(\"BROWSER_USE_THINKING\"" in source


def test_delegator_passes_provider_through_environment_not_code():
    """Lớp giao việc phải chuyển provider qua env, để đổi LLM không cần sửa code."""
    source = DELEGATOR.read_text(encoding="utf-8")
    for key in ("BROWSER_USE_PROVIDER", "BROWSER_USE_MODEL", "BROWSER_USE_BASE_URL", "BROWSER_USE_API_KEY"):
        assert key in source, f"thiếu biến {key}"
    assert "provider_env" in source


def test_delegator_never_touches_cdp_directly():
    """Ranh giới kiến trúc: lớp giao việc KHÔNG được tự điều khiển trình duyệt.

    Nếu file này bắt đầu gọi `Page.navigate` / `Runtime.evaluate` thì nó đã quay lại
    kiểu "LLM điều khiển trực tiếp" mà yêu cầu loại bỏ.

    Soi **mã** (AST), không soi văn bản: docstring của chính file này có nhắc tên các
    lệnh đó để giải thích, và bản đầu của test đã bắt nhầm chính docstring.
    """
    forbidden = {"Page.navigate", "Runtime.evaluate", "Page.captureScreenshot"}

    tree = ast.parse(DELEGATOR.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        # Bắt mọi lời gọi hàm hoặc tham số chuỗi truyền vào hàm.
        if isinstance(node, ast.Call):
            target = node.func
            name = None
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                name = f"{target.value.id}.{target.attr}"
            elif isinstance(target, ast.Name):
                name = target.id
            if name in forbidden:
                offenders.append(name)
            for argument in node.args:
                if isinstance(argument, ast.Constant) and argument.value in forbidden:
                    offenders.append(str(argument.value))
    assert not offenders, f"lớp giao việc không được điều khiển CDP trực tiếp: {offenders}"


def test_worker_reports_structured_result():
    source = WORKER.read_text(encoding="utf-8")
    for key in ('"ok"', '"result"', '"steps"', '"errors"'):
        assert key in source, f"kết quả phải có khoá {key}"


def test_worker_can_attach_to_running_browser():
    """Phải hỗ trợ gắn vào Chrome đang mở để dùng phiên đã đăng nhập CVAT."""
    source = WORKER.read_text(encoding="utf-8")
    assert "cdp_url" in source
    assert "--cdp-url" in source
