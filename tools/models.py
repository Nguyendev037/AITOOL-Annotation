#!/usr/bin/env python3
"""Model registry CLI — bật/tắt model và đồng bộ chúng lên CVAT localhost.

``models.yaml`` là nguồn sự thật duy nhất cho **model nào đang bật**. File này
không quyết định label: label thuộc `taxonomy.yaml`. Một model gắn với label của
mình qua `task`, nên đổi model không kéo theo đổi label và ngược lại.

Usage::

    python tools/models.py list                 # bảng model, task, backend, trạng thái
    python tools/models.py list --json          # cho script khác đọc
    python tools/models.py check                # kiểm registry + đối chiếu taxonomy
    python tools/models.py enable  <id>         # bật
    python tools/models.py disable <id>         # tắt
    python tools/models.py default <id>         # đặt model mặc định cho task của nó
    python tools/models.py sync-cvat --check    # xem trước việc triển khai/gỡ function
    python tools/models.py sync-cvat            # làm thật

Vì sao `sync-cvat` chỉ quản lý một phần function: chỉ model `backend:
model-service` mới có nuclio function. Model `backend: local` (pose17, face50)
chạy trong tiến trình browser-agent, không có gì để triển khai lên CVAT. Lệnh
này **bỏ qua** chúng và nói rõ là bỏ qua, thay vì tạo ra một function rỗng.

Vì sao `--check` không được ghi gì: đây là bài học từ `sync_all.py --check`,
nơi một nhánh vẫn gọi `write=True` và ghi artifact dù người dùng chỉ muốn xem
lệch. Ở đây mọi lệnh ghi đều đi qua đúng một chỗ (`_apply_actions`), và
`--check` trả về trước khi tới đó.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_YAML = ROOT / "models.yaml"
TAXONOMY_YAML = ROOT / "taxonomy.yaml"
FUNCTIONS_DIR = ROOT / "nuclio" / "functions"
DEPLOY_SCRIPT = ROOT / "tools" / "deploy_nuclio.ps1"
DELETE_SCRIPT = ROOT / "tools" / "delete_nuclio.ps1"

VALID_BACKENDS = {"model-service", "local"}
VALID_ANNOTATIONS = {"rectangle", "polygon", "polyline", "points", "skeleton", "mask", "cuboid_3d"}

#: Các biến môi trường được phép dùng trong `checkpoint`. Cho phép khai báo
#: đường dẫn phụ thuộc máy mà không phải sửa file này trên từng máy.
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class RegistryError(RuntimeError):
    """`models.yaml` sai cấu trúc hoặc mâu thuẫn."""


def _force_utf8_output() -> None:
    """Ép stdout/stderr sang UTF-8.

    Không có bước này, mọi dòng tiếng Việt sẽ làm chương trình chết trên Windows:
    console mặc định là cp1252 và `print` ném UnicodeEncodeError ngay giữa bảng
    (đã gặp thật khi chạy `models.py list`). Cùng lớp lỗi với
    `subprocess.run(..., encoding="utf-8")` trong `sync_all.py`.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


@dataclass
class ModelEntry:
    id: str
    task: str
    annotations: str
    backend: str
    handler: str | None = None
    endpoint: str | None = None
    function: str | None = None
    checkpoint: str | None = None
    enabled: bool = True
    default: bool = False
    notes: str = ""

    @property
    def is_remote(self) -> bool:
        return self.backend == "model-service"

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "annotations": self.annotations,
            "backend": self.backend,
            "handler": self.handler,
            "endpoint": self.endpoint,
            "function": self.function,
            "checkpoint": self.checkpoint,
            "enabled": self.enabled,
            "default": self.default,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------- #
# Đọc + kiểm registry
# --------------------------------------------------------------------------- #
def _expand(value: str | None) -> str | None:
    """Thay ``${ENV}`` bằng giá trị môi trường. Biến thiếu -> trả None."""
    if value is None:
        return None
    missing: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        resolved = os.environ.get(name)
        if not resolved:
            missing.append(name)
            return ""
        return resolved

    expanded = _ENV_PATTERN.sub(_sub, value)
    if missing:
        return None
    return expanded


def load_registry(path: Path | None = None) -> list[ModelEntry]:
    # `path=None` rồi mới đọc `REGISTRY_YAML` ở trong thân hàm, KHÔNG dùng
    # `path: Path = REGISTRY_YAML`: giá trị mặc định được gắn lúc import, nên gán
    # lại `models.REGISTRY_YAML` (test, hoặc công cụ khác) sẽ không có tác dụng.
    path = REGISTRY_YAML if path is None else path
    if not path.is_file():
        raise RegistryError(f"không thấy registry: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RegistryError(f"{path.name} không phải YAML hợp lệ: {exc}") from exc
    if not isinstance(data, dict):
        raise RegistryError(f"{path.name} phải là một mapping YAML")
    if not isinstance(data.get("version"), int):
        raise RegistryError(f"{path.name}: `version` phải là số nguyên")

    raw_models = data.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise RegistryError(f"{path.name}: `models` phải là danh sách không rỗng")

    entries: list[ModelEntry] = []
    seen: set[str] = set()
    defaults: dict[str, list[str]] = {}

    for index, raw in enumerate(raw_models, start=1):
        if not isinstance(raw, dict):
            raise RegistryError(f"{path.name}: mục thứ {index} không phải mapping")
        model_id = raw.get("id")
        if not model_id or not isinstance(model_id, str):
            raise RegistryError(f"{path.name}: mục thứ {index} thiếu `id`")
        if model_id in seen:
            raise RegistryError(f"{path.name}: trùng `id` {model_id!r}")
        seen.add(model_id)

        task = raw.get("task")
        if not task or not isinstance(task, str):
            raise RegistryError(f"model {model_id!r}: thiếu `task`")

        annotations = raw.get("annotations")
        if annotations not in VALID_ANNOTATIONS:
            raise RegistryError(
                f"model {model_id!r}: `annotations` {annotations!r} không thuộc "
                f"{sorted(VALID_ANNOTATIONS)}"
            )

        backend = raw.get("backend")
        if backend not in VALID_BACKENDS:
            raise RegistryError(
                f"model {model_id!r}: `backend` {backend!r} không thuộc {sorted(VALID_BACKENDS)}"
            )

        enabled = raw.get("enabled", True)
        is_default = raw.get("default", False)
        if not isinstance(enabled, bool) or not isinstance(is_default, bool):
            raise RegistryError(f"model {model_id!r}: `enabled`/`default` phải là true/false")

        function = raw.get("function")
        if backend == "model-service" and not function:
            raise RegistryError(
                f"model {model_id!r}: backend `model-service` phải khai `function` "
                "(tên nuclio function trên trang Models của CVAT)"
            )
        if backend == "local" and function:
            raise RegistryError(
                f"model {model_id!r}: backend `local` không được khai `function` "
                f"({function!r}); model tại chỗ không có nuclio function"
            )

        entry = ModelEntry(
            id=model_id,
            task=task,
            annotations=annotations,
            backend=backend,
            handler=raw.get("handler"),
            endpoint=raw.get("endpoint"),
            function=function,
            checkpoint=_expand(raw.get("checkpoint")),
            enabled=enabled,
            default=is_default,
            notes=str(raw.get("notes") or "").strip(),
        )
        if entry.default:
            defaults.setdefault(entry.task, []).append(entry.id)
        entries.append(entry)

    for task, ids in sorted(defaults.items()):
        if len(ids) > 1:
            raise RegistryError(
                f"task {task!r} có nhiều hơn một model `default: true`: {', '.join(ids)}"
            )

    # Model đang bật thì mỗi task phải có đúng một mặc định, nếu không lệnh không
    # chỉ định `--model` sẽ mơ hồ. Task tắt hết thì không cần mặc định.
    for task in sorted({entry.task for entry in entries if entry.enabled}):
        enabled_defaults = [e.id for e in entries if e.task == task and e.enabled and e.default]
        if len(enabled_defaults) != 1:
            raise RegistryError(
                f"task {task!r} đang bật nhưng có {len(enabled_defaults)} model mặc định; "
                "cần đúng một `default: true` trong số model đang bật"
            )

    return entries


def taxonomy_tasks(path: Path | None = None) -> set[str]:
    """Các `task` mà `taxonomy.yaml` khai báo (nguồn sự thật của label)."""
    path = TAXONOMY_YAML if path is None else path
    if not path.is_file():
        raise RegistryError(f"không thấy taxonomy: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    groups = data.get("groups") or []
    return {g["task"] for g in groups if isinstance(g, dict) and g.get("task")}


def find_model(entries: list[ModelEntry], model_id: str) -> ModelEntry:
    for entry in entries:
        if entry.id == model_id:
            return entry
    known = ", ".join(entry.id for entry in entries)
    raise RegistryError(f"không có model {model_id!r}; đang có: {known}")


def resolve_model(entries: list[ModelEntry], task: str) -> ModelEntry:
    """Model dùng khi lệnh không chỉ định `--model`: mặc định của task.

    Model đã tắt không bao giờ được trả về — đây là chỗ endpoint và browser-agent
    dùng để từ chối model đã tắt.
    """
    candidates = [e for e in entries if e.task == task and e.enabled]
    if not candidates:
        disabled = [e.id for e in entries if e.task == task]
        detail = (
            f" (có {len(disabled)} model nhưng đã tắt: {', '.join(disabled)})"
            if disabled
            else ""
        )
        raise RegistryError(f"task {task!r} không có model nào đang bật{detail}")
    for entry in candidates:
        if entry.default:
            return entry
    return candidates[0]


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #
def function_specs(dir_path: Path | None = None) -> dict[str, Path]:
    """Map tên nuclio function -> file khai báo nó.

    Tên function (`metadata.name`, ví dụ `smart-bbox`) KHÁC tên file
    (`nuclio/functions/bbox.yaml`). Trộn hai thứ này là lỗi thật đã gặp: kiểm tra
    đi tìm `smart-bbox.yaml` và báo thiếu 4/4 function trong khi chúng vẫn ở đó.
    """
    dir_path = FUNCTIONS_DIR if dir_path is None else dir_path
    specs: dict[str, Path] = {}
    for path in sorted(dir_path.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        name = (data.get("metadata") or {}).get("name")
        if name:
            specs[str(name)] = path
    return specs


def check_registry(entries: list[ModelEntry] | None = None) -> list[str]:
    """Trả về danh sách vấn đề. Rỗng nghĩa là registry khớp thực tế."""
    problems: list[str] = []
    entries = load_registry() if entries is None else entries
    declared = taxonomy_tasks()
    specs = function_specs()

    seen_functions: dict[str, str] = {}
    for entry in entries:
        if entry.task not in declared:
            problems.append(
                f"model {entry.id!r}: task {entry.task!r} không có trong taxonomy.yaml "
                f"(đang có: {', '.join(sorted(declared))})"
            )
        if entry.is_remote:
            other = seen_functions.get(entry.function or "")
            if other:
                problems.append(
                    f"model {entry.id!r} và {other!r} cùng dùng nuclio function "
                    f"{entry.function!r}; mỗi function chỉ phục vụ một model"
                )
            else:
                seen_functions[entry.function or ""] = entry.id
            if entry.function not in specs:
                known = ", ".join(sorted(specs)) or "không có file nào"
                problems.append(
                    f"model {entry.id!r}: không có nuclio function {entry.function!r} "
                    f"trong nuclio/functions/ (đang có: {known})"
                )
        if entry.checkpoint and not entry.checkpoint.startswith("mediapipe:"):
            path = Path(entry.checkpoint)
            if not path.is_absolute():
                path = ROOT / path
            if not path.exists():
                problems.append(
                    f"model {entry.id!r}: không thấy checkpoint {entry.checkpoint}"
                )
    return problems


# --------------------------------------------------------------------------- #
# sync-cvat
# --------------------------------------------------------------------------- #
@dataclass
class SyncAction:
    kind: str          # deploy | delete
    function: str
    model_id: str
    reason: str = ""


def plan_sync(entries: list[ModelEntry], *, present: set[str] | None = None) -> tuple[list[SyncAction], list[str]]:
    """Việc cần làm để CVAT khớp registry. Trả về (actions, ghi chú bỏ qua).

    ``present`` là tập function đang có trên dashboard. ``None`` nghĩa là chưa
    đọc được dashboard: khi đó chỉ lên kế hoạch deploy model đang bật, không gỡ
    gì, vì gỡ dựa trên thông tin không đọc được là đoán.
    """
    actions: list[SyncAction] = []
    skipped: list[str] = []

    for entry in entries:
        if not entry.is_remote:
            skipped.append(
                f"{entry.id}: backend `local` — không có function để quản lý trên CVAT"
            )
            continue
        if entry.enabled:
            actions.append(
                SyncAction("deploy", entry.function or "", entry.id, "model đang bật")
            )

    if present is not None:
        owned = {e.function for e in entries if e.is_remote and e.function}
        for name in sorted(present & owned):
            entry = next(e for e in entries if e.function == name)
            if not entry.enabled:
                actions.append(
                    SyncAction("delete", name, entry.id, "model đã tắt")
                )
    return actions, skipped


def _read_dashboard_functions() -> set[str] | None:
    """Đọc danh sách function trên nuclio dashboard. None nếu không đọc được.

    Cố ý trả None thay vì ném lỗi: Docker có thể đang tắt, và khi đó `sync-cvat`
    vẫn phải nói được kế hoạch deploy thay vì đổ.
    """
    script = f"""
import json, urllib.request
try:
    with urllib.request.urlopen("http://nuclio:8070/api/functions", timeout=10) as r:
        data = json.load(r)
except Exception as exc:
    print("ERR", exc); raise SystemExit(3)
names = sorted({{f.get("metadata", {{}}).get("name", "") for f in data.get("functions", [])}} - {{""}})
print(json.dumps(names))
"""
    docker = subprocess.run(
        ["docker", "run", "--rm", "--network", "cvat_cvat", "python:3.12-alpine",
         "python", "-c", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if docker.returncode != 0:
        return None
    for line in reversed((docker.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("["):
            try:
                return set(json.loads(line))
            except json.JSONDecodeError:
                return None
    return None


def _run_powershell(script: Path, name: str, *, whatif: bool) -> int:
    args = [
        "powershell", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Name", name
    ]
    if whatif:
        args.append("-WhatIf")
    completed = subprocess.run(
        args, cwd=ROOT, text=True, encoding="utf-8", errors="replace"
    )
    return completed.returncode


def _apply_actions(actions: list[SyncAction], *, whatif: bool) -> int:
    """CHỖ DUY NHẤT ghi ra ngoài. `--check` không bao giờ tới được đây."""
    code = 0
    for action in actions:
        script = DEPLOY_SCRIPT if action.kind == "deploy" else DELETE_SCRIPT
        verb = "triển khai" if action.kind == "deploy" else "gỡ"
        print(f"  {verb} {action.function} ({action.model_id}: {action.reason})")
        if action.kind == "deploy":
            generated = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "deploy_nuclio.py"),
                 "--function", action.function],
                cwd=ROOT, text=True, encoding="utf-8", errors="replace",
            )
            if generated.returncode != 0:
                code = generated.returncode
                continue
        if whatif:
            continue
        result = _run_powershell(script, action.function, whatif=False)
        if result != 0:
            code = result
    return code


# --------------------------------------------------------------------------- #
# enable / disable / default — sửa models.yaml
# --------------------------------------------------------------------------- #
def set_flag(model_id: str, field: str, value: bool) -> None:
    """Đổi `enabled`/`default` của một model trong `models.yaml`.

    Sửa bằng cách thay đúng dòng đó trong văn bản gốc, không `yaml.safe_dump`:
    dump sẽ xoá sạch phần chú thích giải thích của file, mà đó là phần đáng giá
    nhất của nó. Cùng lý do `sync_taxonomy.py` dùng marker thay vì dump lại YAML.
    """
    entries = load_registry()
    entry = find_model(entries, model_id)
    if field == "default" and value and not entry.enabled:
        raise RegistryError(
            f"model {model_id!r} đang tắt; bật trước rồi mới đặt làm mặc định"
        )

    text = REGISTRY_YAML.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    # Tìm đúng khối của model này: từ dòng `- id: <id>` tới `- id:` kế tiếp.
    start = None
    for index, line in enumerate(lines):
        if re.match(rf"^\s*-\s*id:\s*{re.escape(model_id)}\s*$", line):
            start = index
            break
    if start is None:
        raise RegistryError(f"không thấy dòng `- id: {model_id}` trong {REGISTRY_YAML.name}")

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^\s*-\s*id:\s*\S+", lines[index]):
            end = index
            break

    pattern = re.compile(rf"^(\s*){field}:\s*(true|false)\s*$")
    for index in range(start, end):
        match = pattern.match(lines[index])
        if match:
            indent = match.group(1)
            lines[index] = f"{indent}{field}: {'true' if value else 'false'}\n"
            break
    else:
        # Chưa có dòng đó: chèn ngay sau `backend:` cho dễ đọc.
        for index in range(start, end):
            if re.match(r"^\s*backend:\s*\S+", lines[index]):
                indent = re.match(r"^(\s*)", lines[index]).group(1)
                lines.insert(index + 1, f"{indent}{field}: {'true' if value else 'false'}\n")
                break
        else:
            raise RegistryError(f"model {model_id!r}: không tìm được chỗ chèn `{field}`")

    REGISTRY_YAML.write_text("".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cmd_list(entries: list[ModelEntry], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps([entry.as_dict() for entry in entries], indent=2, ensure_ascii=False))
        return 0
    print(f"{'id':<22} {'task':<10} {'annotations':<11} {'backend':<14} {'function':<15} state")
    print("-" * 96)
    for entry in entries:
        state = "bật" if entry.enabled else "TẮT"
        if entry.enabled and entry.default:
            state += " (mặc định)"
        print(
            f"{entry.id:<22} {entry.task:<10} {entry.annotations:<11} "
            f"{entry.backend:<14} {entry.function or '—':<15} {state}"
        )
    enabled = sum(1 for e in entries if e.enabled)
    print(f"\n{enabled}/{len(entries)} model đang bật. Nguồn: models.yaml")
    return 0


def _cmd_check(entries: list[ModelEntry]) -> int:
    problems = check_registry(entries)
    if problems:
        print("LỆCH:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    remote = sum(1 for e in entries if e.is_remote)
    local = len(entries) - remote
    print(f"OK: {len(entries)} model ({remote} qua model-service, {local} chạy tại chỗ)")
    for task in sorted({e.task for e in entries}):
        try:
            chosen = resolve_model(entries, task)
            print(f"  {task:<10} -> {chosen.id}")
        except RegistryError:
            print(f"  {task:<10} -> (không có model đang bật)")
    return 0


def _cmd_sync_cvat(entries: list[ModelEntry], *, check: bool) -> int:
    present = _read_dashboard_functions()
    if present is None:
        print(
            "Chú ý: không đọc được nuclio dashboard (Docker đang tắt?). "
            "Chỉ lên kế hoạch triển khai, không gỡ function nào.",
            file=sys.stderr,
        )
    actions, skipped = plan_sync(entries, present=present)

    if skipped:
        print("Bỏ qua (không có function trên CVAT):")
        for note in skipped:
            print(f"  - {note}")

    if not actions:
        print("Không có gì để làm: CVAT đã khớp registry.")
        return 0

    print("\nViệc cần làm:" if not check else "\nViệc SẼ làm (--check, không ghi gì):")
    for action in actions:
        verb = "triển khai" if action.kind == "deploy" else "gỡ"
        print(f"  - {verb} {action.function}  [{action.model_id}: {action.reason}]")

    if check:
        return 0
    print()
    return _apply_actions(actions, whatif=False)


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="liệt kê model")
    p_list.add_argument("--json", action="store_true", help="in JSON")

    sub.add_parser("check", help="kiểm registry và đối chiếu taxonomy.yaml")

    p_enable = sub.add_parser("enable", help="bật một model")
    p_enable.add_argument("model_id")
    p_disable = sub.add_parser("disable", help="tắt một model")
    p_disable.add_argument("model_id")
    p_default = sub.add_parser("default", help="đặt model mặc định cho task của nó")
    p_default.add_argument("model_id")

    p_sync = sub.add_parser("sync-cvat", help="triển khai/gỡ function theo registry")
    p_sync.add_argument("--check", action="store_true", help="chỉ in kế hoạch, không ghi gì")

    args = parser.parse_args(argv)
    try:
        entries = load_registry()
    except RegistryError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2

    if args.command == "list":
        return _cmd_list(entries, as_json=args.json)
    if args.command == "check":
        return _cmd_check(entries)
    if args.command == "sync-cvat":
        return _cmd_sync_cvat(entries, check=args.check)

    try:
        if args.command == "enable":
            set_flag(args.model_id, "enabled", True)
        elif args.command == "disable":
            set_flag(args.model_id, "enabled", False)
        elif args.command == "default":
            set_flag(args.model_id, "default", True)
    except RegistryError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2

    # Đọc lại để chắc chắn file vừa sửa vẫn hợp lệ, không chỉ tin là đã sửa.
    try:
        entries = load_registry()
    except RegistryError as exc:
        print(
            f"LỖI: sau khi sửa, models.yaml không còn hợp lệ: {exc}\n"
            "     Sửa tay lại file này.",
            file=sys.stderr,
        )
        return 2
    print(f"Đã cập nhật {args.model_id}:")
    return _cmd_list(entries, as_json=False)


if __name__ == "__main__":
    sys.exit(main())
