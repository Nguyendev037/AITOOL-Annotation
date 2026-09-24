#!/usr/bin/env python3
"""Lái CVAT bằng trình duyệt thật qua CDP — đường thứ hai, để đối chiếu REST.

    python tools/agent_browser.py --check
    python tools/agent_browser.py --url http://localhost:8080/tasks
    python tools/agent_browser.py --shot work/ui.png
    python tools/agent_browser.py --sel "#task-list" --text

Vì sao vẫn cần đường này dù REST đã chạy: REST cho biết *trạng thái*, còn trình
duyệt cho biết *người dùng nhìn thấy gì*. Hai đường lệch nhau là dấu hiệu lỗi mà
một mình REST không phát hiện được (ví dụ: annotation đã ghi nhưng UI không vẽ).

Cách nói chuyện: **CDP thẳng qua WebSocket**, không qua Playwright. Lý do: venv lõi
có `playwright` nhưng **chưa tải browser nào** (`ms-playwright` không tồn tại), mà
Chrome thì đã có sẵn trên máy. Nói CDP trực tiếp tránh được một lần tải ~150MB và
tránh phụ thuộc vào bản Chromium của Playwright.

⚠️ Chrome bị sandbox của DSH chặn khi chạy ở chế độ workspace-write: tiến trình
thoát ngay với exit code lạ. Phải chạy các lệnh này với quyền rộng hơn.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover
            pass

from browser_agent.cdp_ws import CdpConnection  # noqa: E402
from browser_agent.config import browser_settings  # noqa: E402

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def find_browser() -> Path:
    for candidate in CHROME_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return path
    raise SystemExit("Không thấy Chrome/Edge. Cài Chrome hoặc sửa CHROME_CANDIDATES.")


def one_shot(url: str, *, dump_dom: bool, shot: Path | None, profile: Path, budget_ms: int = 6000) -> str:
    """Điều hướng một lần bằng chính Chrome, KHÔNG cần websocket.

    Vì sao chọn cách này làm đường chính: repo không cài được `websocket-client`
    (PyPI bị chặn) nên CDP-qua-WebSocket cần một gói nữa. Chrome có sẵn hai cờ làm
    đúng việc cần — ``--dump-dom`` (in DOM sau khi render) và ``--screenshot`` — nên
    đường lái UI không phụ thuộc gói ngoài nào.

    ``--virtual-time-budget`` cho trang thời gian ảo để chạy JS/nạp dữ liệu trước
    khi chụp, thay vì ngủ mù.
    """
    browser = find_browser()
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        "--headless=new",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-gpu",
        f"--virtual-time-budget={budget_ms}",
        "--window-size=1600,1000",
    ]
    if dump_dom:
        args.append("--dump-dom")
    if shot is not None:
        # Phải là đường dẫn TUYỆT ĐỐI: Chrome ghi file tương đối theo thư mục làm
        # việc của nó, không phải cwd của tiến trình gọi, nên ảnh "chụp thành công"
        # sẽ biến mất. Đã gặp thật.
        shot = shot.resolve()
        shot.parent.mkdir(parents=True, exist_ok=True)
        args.append(f"--screenshot={shot}")
    args.append(url)

    completed = subprocess.run(
        [str(browser), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )
    if completed.returncode != 0 and not (dump_dom and completed.stdout):
        raise SystemExit(
            f"trình duyệt lỗi (exit={completed.returncode}):\n{completed.stderr[-800:]}\n"
            "Nếu đang chạy trong sandbox workspace-write, Chrome bị chặn — cần quyền rộng hơn."
        )
    return completed.stdout


def cdp_http(port: int, path: str, *, timeout: float = 8.0) -> dict:
    with urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def is_alive(port: int) -> dict | None:
    try:
        return cdp_http(port, "/json/version")
    except (URLError, OSError, json.JSONDecodeError):
        return None


def launch(port: int, *, profile: Path, headless: bool = False) -> int:
    """Mở trình duyệt với cổng debug. Trả về pid."""
    existing = is_alive(port)
    if existing:
        print(f"đã có trình duyệt ở cổng {port}: {existing.get('Browser')}")
        return 0

    browser = find_browser()
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        "about:blank",
    ]
    if headless:
        args.insert(0, "--headless=new")
    process = subprocess.Popen(
        [str(browser), *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        # stdio piped sẽ bị sandbox chặn; DEVNULL thì không.
    )
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(
                f"trình duyệt thoát ngay (exit={process.returncode}). Nếu đang chạy trong "
                "sandbox workspace-write thì đây là dấu hiệu bị chặn — cần quyền rộng hơn."
            )
        info = is_alive(port)
        if info:
            print(f"trình duyệt sẵn sàng: {info.get('Browser')}")
            return process.pid
        time.sleep(0.5)
    raise SystemExit(f"hết thời gian chờ cổng debug {port}")


# --------------------------------------------------------------------------- #
# CDP qua WebSocket
# --------------------------------------------------------------------------- #
class Session:
    """Một tab CDP. Đóng lại khi xong."""

    def __init__(self, ws_url: str, *, timeout: float = 30.0) -> None:
        # Dùng WebSocket tự viết trong repo (`browser_agent/cdp_ws.py`) vì gói
        # `websocket-client` không cài được (PyPI bị chặn).
        self._conn = CdpConnection(ws_url, timeout=timeout)

    def call(self, method: str, **params) -> dict:
        return self._conn.call(method, **params)

    def evaluate(self, expression: str):
        result = self.call(
            "Runtime.evaluate",
            expression=expression,
            returnByValue=True,
            awaitPromise=True,
        )
        if "exceptionDetails" in result:
            raise RuntimeError(f"JS lỗi: {result['exceptionDetails'].get('text')}")
        return result.get("result", {}).get("value")

    def goto(self, url: str, *, settle: float = 2.5) -> None:
        self.call("Page.navigate", url=url)
        time.sleep(settle)

    def screenshot(self, path: Path) -> None:
        result = self.call("Page.captureScreenshot", format="png")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(result["data"]))

    def close(self) -> None:
        self._conn.close()


def open_tab(port: int, url: str = "about:blank") -> Session:
    """Mở tab mới và trả về Session đã attach."""
    created = cdp_http(port, f"/json/new?{url}", timeout=15) if url != "about:blank" else None
    if created is None:
        # Cách ổn định nhất: lấy tab đang có, nếu không có thì tạo mới.
        targets = [t for t in cdp_http(port, "/json/list") if t.get("type") == "page"]
        if not targets:
            created = cdp_http(port, "/json/new", timeout=15)
        else:
            created = targets[0]
    session = Session(created["webSocketDebuggerUrl"])
    session.call("Page.enable")
    session.call("Runtime.enable")
    return session


def _attach_hint(port: int, profile: Path) -> str:
    """Lệnh để người dùng mở lại Chrome của họ kèm cổng debug."""
    browser = "chrome.exe"
    return (
        f'  & "{browser}" --remote-debugging-port={port} '
        f'--user-data-dir="$env:LOCALAPPDATA\\Google\\Chrome\\User Data"\n'
        f"  (profile riêng của agent: {profile})"
    )


#: JS điền giá trị vào input theo cách React nhận ra.
#: Gán thẳng `.value` sẽ bị React bỏ qua (nó theo dõi setter gốc), nên phải gọi
#: setter của prototype rồi tự phát event `input`/`change`. Đây là lý do phổ biến
#: khiến "điền form bằng JS" thất bại im lặng trên các SPA.
_FILL_JS = """
(() => {
  const el = document.querySelector(%(sel)s);
  if (!el) return 'KHONG_THAY';
  const proto = el instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
  setter.call(el, %(value)s);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return 'OK';
})()
"""

_CLICK_JS = """
(() => {
  const el = document.querySelector(%(sel)s);
  if (!el) return 'KHONG_THAY';
  el.click();
  return 'OK';
})()
"""


def _js(script: str, **values) -> str:
    return script % {key: json.dumps(value) for key, value in values.items()}


def login_cvat(session: "Session", url: str, username: str, password: str) -> bool:
    """Đăng nhập CVAT bằng form. Trả True nếu đã vào được trong.

    CVAT đăng nhập **hai bước**, không phải một: nhập tài khoản -> bấm "Next" ->
    ô mật khẩu mới xuất hiện -> nhập mật khẩu -> bấm "Next". Bản đầu của hàm này
    điền cả hai ô một lượt nên không bao giờ thấy `#password` (nó chưa tồn tại) và
    thất bại im lặng — đã dò bằng `work/probe_login.py` mới biết.
    """
    session.goto(url, settle=5.0)

    def body_text() -> str:
        return session.evaluate("document.body.innerText.slice(0, 4000)") or ""

    if "Password" not in body_text():
        outcome = session.evaluate(_js(_FILL_JS, sel="#credential", value=username))
        print(f"  điền #credential: {outcome}")
        if outcome == "KHONG_THAY":
            print("KHÔNG thấy ô tài khoản — trang đăng nhập đã đổi", file=sys.stderr)
            return False
        session.evaluate(_js(_CLICK_JS, sel="button[type=submit]"))
        time.sleep(3)
        if "Password" not in body_text():
            print("bấm Next nhưng ô mật khẩu không xuất hiện", file=sys.stderr)
            return False

    outcome = session.evaluate(_js(_FILL_JS, sel="#password", value=password))
    print(f"  điền #password: {outcome}")
    if outcome == "KHONG_THAY":
        print("KHÔNG thấy ô mật khẩu", file=sys.stderr)
        return False
    session.evaluate(_js(_CLICK_JS, sel="button[type=submit]"))
    time.sleep(6)

    text = body_text()
    if "Please specify a password" in text or "Sign in" in text:
        print("vẫn ở trang đăng nhập — sai tài khoản hoặc mật khẩu", file=sys.stderr)
        return False
    return True


def main() -> int:
    settings = browser_settings()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="chỉ kiểm tra kết nối CDP")
    parser.add_argument(
        "--attach",
        action="store_true",
        help="gắn vào trình duyệt ĐANG MỞ (dùng phiên đã đăng nhập), cần cổng debug",
    )
    parser.add_argument("--launch", action="store_true", help="mở trình duyệt nếu chưa có")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--url", default=None, help="điều hướng tới URL này")
    parser.add_argument("--dom", action="store_true", help="in DOM sau khi render (không cần websocket)")
    parser.add_argument("--shot", default=None, help="chụp màn hình ra file PNG")
    parser.add_argument("--login", action="store_true", help="đăng nhập CVAT bằng form")
    parser.add_argument("--user", default=None, help="tên đăng nhập CVAT")
    parser.add_argument("--password", default=None, help="mật khẩu CVAT")
    parser.add_argument("--expect", default=None, help="chuỗi phải có trong DOM (kiểm chứng)")
    parser.add_argument("--sel", default=None, help="selector CSS cần đọc")
    parser.add_argument("--text", action="store_true", help="in text của --sel")
    parser.add_argument("--title", action="store_true", help="in tiêu đề trang")
    parser.add_argument("--profile", default=None, help="thư mục profile trình duyệt")
    args = parser.parse_args()

    port = 9222
    if ":" in settings.cdp_url.rsplit("/", 1)[-1]:
        port = int(settings.cdp_url.rsplit(":", 1)[-1])

    profile = Path(args.profile) if args.profile else Path(settings.core_dir / "chrome-profile")

    # Đường chính: một lần chạy Chrome, không cần websocket.
    if args.dom or args.shot:
        if not args.url:
            print("--dom/--shot cần --url", file=sys.stderr)
            return 2
        dom = one_shot(
            args.url,
            dump_dom=args.dom,
            shot=Path(args.shot) if args.shot else None,
            profile=profile,
        )
        if args.shot:
            print(f"đã chụp {args.shot}")
        if args.dom:
            print(f"DOM: {len(dom)} ký tự")
            if args.expect:
                found = args.expect in dom
                print(f"kỳ vọng {args.expect!r}: {'CÓ' if found else 'KHÔNG THẤY'}")
                if not found:
                    return 1
            else:
                print(dom[:4000])
        return 0

    if args.attach:
        # Gắn vào Chrome đang mở của người dùng: cách duy nhất để dùng phiên đã
        # đăng nhập CVAT mà không cần token. Chrome phải được khởi động với
        # --remote-debugging-port; nếu chưa thì báo rõ cách làm.
        info = is_alive(port)
        if info is None:
            print(f"KHÔNG thấy cổng debug {port} — Chrome đang mở nhưng chưa bật CDP.", file=sys.stderr)
            print("Đóng hết Chrome rồi mở lại bằng:", file=sys.stderr)
            print(_attach_hint(port, profile), file=sys.stderr)
            return 2
        print(f"đã gắn vào: {info.get('Browser')}")
        targets = [t for t in cdp_http(port, "/json/list") if t.get("type") == "page"]
        if not targets:
            print("không có tab nào đang mở", file=sys.stderr)
            return 2
        if args.url:
            target = targets[0]
            print(f"tab: {target.get('url', '')[:100]}")
        else:
            for index, target in enumerate(targets):
                print(f"  [{index}] {target.get('title', '')[:60]} — {target.get('url', '')[:80]}")
            return 0

        session = Session(targets[0]["webSocketDebuggerUrl"])
        try:
            if args.login:
                if not (args.user and args.password):
                    print("--login cần --user và --password", file=sys.stderr)
                    return 2
                base = args.url or "https://cvat.note.transformerlabs.ai"
                login_url = base.split("/tasks/")[0].rstrip("/") + "/auth/login"
                print(f"đăng nhập tại {login_url}")
                if not login_cvat(session, login_url, args.user, args.password):
                    if args.shot:
                        session.screenshot(Path(args.shot).resolve())
                        print(f"đã chụp màn hình lỗi {args.shot}")
                    return 3
                print("đăng nhập OK")

            if args.url:
                session.goto(args.url, settle=4.0)
                print("title:", session.evaluate("document.title"))
            if args.sel and args.text:
                text = session.evaluate(
                    "(() => { const el = document.querySelector(%s); return el ? el.innerText : null; })()"
                    % json.dumps(args.sel)
                )
                print(text if text is not None else "(không thấy phần tử)")
            if args.shot:
                path = Path(args.shot).resolve()
                session.screenshot(path)
                print(f"đã chụp {path}")
        finally:
            session.close()
        return 0

    if args.launch:
        launch(port, profile=profile, headless=args.headless)

    info = is_alive(port)
    if info is None:
        print(f"KHÔNG kết nối được CDP ở cổng {port}.", file=sys.stderr)
        print("Chạy lại với --launch (và cần quyền rộng hơn nếu đang trong sandbox).", file=sys.stderr)
        return 2
    print(f"CDP OK cổng {port}: {info.get('Browser')}")

    if args.check and not (args.url or args.shot or args.sel or args.title):
        return 0

    session = open_tab(port, args.url or "about:blank")
    try:
        if args.url:
            session.goto(args.url)
        if args.title:
            print("title:", session.evaluate("document.title"))
        if args.sel and args.text:
            text = session.evaluate(
                "(() => { const el = document.querySelector(%s); return el ? el.innerText : null; })()"
                % json.dumps(args.sel)
            )
            print(f"text của {args.sel!r}:")
            print(text if text is not None else "(không thấy phần tử)")
        if args.shot:
            path = Path(args.shot)
            session.screenshot(path)
            print(f"đã chụp {path}")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
