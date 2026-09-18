#!/usr/bin/env python3
"""Compare CVAT task labels against the project taxonomy, and optionally fix them.

CVAT maps a model's labels onto a task's labels **by exact name string**
(``cvat/apps/lambda_manager/views.py``), and silently drops every model label it
cannot map::

    if item_label not in mapping:
        continue

so a one-character mismatch (``traffic light`` vs ``traffic_light``) produces
zero shapes with no error message. This tool makes that failure visible before
auto-annotation runs.

It also mirrors CVAT's own compatibility rule, verified in the installed source::

    compatible_types = [[ShapeType.MASK, ShapeType.POLYGON]]
    model_type == db_type
      or (db_type == "any" and model_type != "skeleton")
      or (model_type == "any" and db_type != "skeleton")
      or (model/polygon types in the same compatible group)

which means a task label declared as ``type: any`` accepts our polygon and
rectangle output unchanged.

Usage
-----
    python tools/cvat_labels.py list
    python tools/cvat_labels.py check                 # every task, read-only
    python tools/cvat_labels.py check --task 13
    python tools/cvat_labels.py add --task 13 --group semantic          # dry run
    python tools/cvat_labels.py add --task 13 --group semantic --yes    # applies

Credentials (first match wins):
    --token / CVAT_LOCAL_TOKEN      a DRF token
    --username + --password         logged in via POST /api/auth/login
    CVAT_LOCAL_USERNAME / CVAT_LOCAL_PASSWORD

Only the standard library is used.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from sync_taxonomy import build_runtime, load_taxonomy  # noqa: E402

DEFAULT_URL = "http://localhost:8080"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Fill ``os.environ`` from ``.env`` — the convention this repo already uses
    (Docker Compose reads the same file). Real environment variables win, so CI
    or a one-off ``$env:CVAT_LOCAL_TOKEN`` still overrides the file.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class CvatError(RuntimeError):
    pass


class Cvat:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, body: dict | None = None):
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", f"Token {self.token}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:600]
            raise CvatError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise CvatError(f"{method} {path} -> {exc.reason}") from exc
        return json.loads(raw) if raw.strip() else None

    def get(self, path: str):
        return self.request("GET", path)

    def patch(self, path: str, body: dict):
        return self.request("PATCH", path, body)


def resolve_token(args) -> str:
    token = args.token or os.environ.get("CVAT_LOCAL_TOKEN", "").strip()
    if token:
        return token

    username = args.username or os.environ.get("CVAT_LOCAL_USERNAME", "").strip()
    password = args.password or os.environ.get("CVAT_LOCAL_PASSWORD", "")
    if not (username and password):
        raise SystemExit(
            "no credentials. Set CVAT_LOCAL_TOKEN, or pass --username/--password.\n"
            "Mint a token with:\n"
            "  docker exec cvat_server python manage.py drf_create_token <username>"
        )

    request = urllib.request.Request(
        f"{args.url.rstrip('/')}/api/auth/login",
        data=json.dumps({"username": username, "password": password}).encode("utf-8"),
        method="POST",
    )
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))["key"]
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"login failed: HTTP {exc.code}") from exc


# ---------------------------------------------------------------------------
# CVAT shape compatibility (mirrors lambda_manager/views.py)
# ---------------------------------------------------------------------------

COMPATIBLE_GROUPS = [{"mask", "polygon"}]


def labels_compatible(model_type: str, db_type: str) -> bool:
    if model_type == db_type:
        return True
    if db_type == "any" and model_type != "skeleton":
        return True
    if model_type == "any" and db_type != "skeleton":
        return True
    return any(model_type in group and db_type in group for group in COMPATIBLE_GROUPS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_tasks(cvat: Cvat) -> list[dict]:
    tasks: list[dict] = []
    page = 1
    while True:
        payload = cvat.get(f"/api/tasks?page={page}&page_size=100")
        tasks.extend(payload.get("results") or [])
        if not payload.get("next"):
            return tasks
        page += 1


def fetch_labels(cvat: Cvat, *, task_id: int | None = None, project_id: int | None = None) -> list[dict]:
    if task_id is not None:
        query = f"task_id={task_id}"
    elif project_id is not None:
        query = f"project_id={project_id}"
    else:
        return []
    payload = cvat.get(f"/api/labels?{query}&page_size=200")
    return payload.get("results") or []


def cover(group: dict, task_labels: list[dict]) -> tuple[int, list[str], list[tuple[str, str]]]:
    """Return (usable count, missing names, name clashes with an incompatible type).

    A name that exists but has an incompatible shape type is NOT usable: CVAT's
    `labels_compatible` rejects it and the label is dropped just like a missing
    one. Counting it as a match would overstate what the model can actually do.
    """
    missing: list[str] = []
    clashes: list[tuple[str, str]] = []
    usable = 0
    by_name = {label["name"]: label for label in task_labels}
    for label in group["labels"]:
        task_label = by_name.get(label["name"])
        if task_label is None:
            missing.append(label["name"])
        elif labels_compatible(group["shape"], task_label.get("type") or "any"):
            usable += 1
        else:
            clashes.append((label["name"], task_label.get("type") or "any"))
    return usable, missing, clashes


def hex_color(rgb: list[int] | None, name: str) -> str:
    if rgb:
        return "#{:02x}{:02x}{:02x}".format(*rgb)
    # Deterministic colour for labels the taxonomy gives no preview colour for.
    digest = 0
    for char in name:
        digest = (digest * 131 + ord(char)) & 0xFFFFFF
    return f"#{digest:06x}"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(cvat: Cvat, runtime: dict, args) -> int:
    tasks = fetch_tasks(cvat)
    if not tasks:
        print("no tasks on this CVAT instance")
        return 0
    for task in tasks:
        labels = fetch_labels(cvat, task_id=task["id"])
        project = f" project={task['project_id']}" if task.get("project_id") else ""
        print(f"task {task['id']:>4}  [{task['name']}]  size={task['size']}{project}  labels={len(labels)}")
    return 0


def cmd_check(cvat: Cvat, runtime: dict, args) -> int:
    tasks = fetch_tasks(cvat)
    if args.task:
        tasks = [task for task in tasks if task["id"] in set(args.task)]
        if not tasks:
            raise SystemExit(f"no such task: {args.task}")

    only = set(args.group or [])
    groups = [group for group in runtime["groups"] if not only or group["id"] in only]
    report: list[dict] = []
    problems = 0

    for task in tasks:
        labels = fetch_labels(cvat, task_id=task["id"])
        declared = {label["name"] for label in labels}
        project = f"  (project {task['project_id']})" if task.get("project_id") else ""
        print(f"\ntask {task['id']}  [{task['name']}]  {task['size']} ảnh{project}")
        if not labels:
            print("    ⚠ task không có label nào — auto-annotation sẽ không tạo được shape")
            problems += 1
            continue

        for group in groups:
            usable, missing, clashes = cover(group, labels)
            total = len(group["labels"])
            function = group.get("function") or "(không có model)"
            task_entry = runtime["tasks"].get(group.get("task") or "")

            if group.get("supported") is False:
                status = "n/a    "
            elif usable == total:
                status = "OK     "
            elif usable == 0:
                status = "HỎNG   "
            else:
                status = "MỘT PHẦN"

            print(
                f"    {status} {group['id']:<9} {group['shape']:<9} {function:<16} "
                f"{usable}/{total} label dùng được"
            )
            if missing and args.verbose:
                shown = ", ".join(missing[:8]) + (" …" if len(missing) > 8 else "")
                print(f"          thiếu: {shown}")
            for name, db_type in clashes:
                print(f"          ⚠ '{name}' có type={db_type}, không nhận {group['shape']}")
            if group.get("supported") is False:
                continue
            if usable == 0 and task_entry:
                problems += 1

            report.append({
                "task_id": task["id"],
                "task_name": task["name"],
                "group": group["id"],
                "function": function,
                "shape": group["shape"],
                "declared_labels": total,
                "usable_labels": usable,
                "missing": missing,
                "type_clashes": [{"name": n, "task_type": t} for n, t in clashes],
                "usable": usable > 0,
            })

    if args.json:
        print(json.dumps({"tasks": report}, indent=2, ensure_ascii=False))
    else:
        print(
            "\nNhắc lại: CVAT map label theo đúng tên chuỗi và BỎ IM LẶNG label không khớp "
            "(lambda_manager/views.py: `if item_label not in mapping: continue`)."
        )
        print(f"'HỎNG' = không label nào của model khớp task. Số nhóm như vậy: {problems}")
        print("Label type 'any' của task VẪN nhận polygon/rectangle — không phải lỗi.")
    return 0


def cmd_add(cvat: Cvat, runtime: dict, args) -> int:
    # `--group` is append=True because `check` accepts several; `add` takes one.
    if len(args.group or []) != 1:
        raise SystemExit("`add` needs exactly one --group <id>")
    group_id = args.group[0]
    group = next((g for g in runtime["groups"] if g["id"] == group_id), None)
    if group is None:
        raise SystemExit(
            f"unknown group {group_id!r}; available: "
            + ", ".join(g["id"] for g in runtime["groups"])
        )
    if group.get("supported") is False and not args.force:
        raise SystemExit(
            f"group {group['id']!r} has no model behind it "
            f"({group.get('unsupported_reason')}). Re-run with --force if you still "
            "want the labels declared on the task."
        )

    if len(args.task or []) != 1:
        raise SystemExit("`add` needs exactly one --task <id>")
    task_id = args.task[0]

    task = cvat.get(f"/api/tasks/{task_id}")
    project_id = task.get("project_id")
    target = f"/api/projects/{project_id}" if project_id else f"/api/tasks/{task_id}"
    scope = "project" if project_id else "task"
    existing = fetch_labels(cvat, task_id=None if project_id else task_id, project_id=project_id)

    existing_names = {label["name"] for label in existing}
    missing = [label for label in group["labels"] if label["name"] not in existing_names]
    if not missing:
        print(f"task {task_id}: group {group['id']!r} đã có đủ {len(group['labels'])} label — không cần làm gì")
        return 0

    shape = args.shape or group["shape"]
    # Send existing labels back verbatim (id + name + colour only) so CVAT updates
    # them in place instead of recreating, then append the missing ones.
    payload_labels = [
        {"id": label["id"], "name": label["name"], "color": label["color"]}
        for label in existing
    ] + [
        {"name": label["name"], "color": hex_color(label.get("color"), label["name"]), "type": shape}
        for label in missing
    ]

    print(f"task {task_id} [{task['name']}] — label đến từ {scope} {project_id or task_id}")
    print(f"  thêm {len(missing)} label ({shape}): {', '.join(l['name'] for l in missing)}")
    if project_id:
        print(
            f"  ⚠ PATCH {target} sửa label của CẢ DỰ ÁN {project_id}, "
            "tức mọi task thuộc dự án này."
        )
    print(f"  PATCH {target}  →  {len(payload_labels)} label tổng cộng")

    if not args.yes:
        print("\n(dry run) Thêm --yes để áp dụng thật.")
        if args.dump:
            print(json.dumps({"labels": payload_labels}, indent=2, ensure_ascii=False))
        return 0

    cvat.patch(target, {"labels": payload_labels})
    print("  đã áp dụng. Kiểm tra lại bằng: python tools/cvat_labels.py check --task", task_id)
    return 0


# ---------------------------------------------------------------------------

def main() -> int:
    # The Windows console defaults to cp1252 and would crash on Vietnamese text.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", choices=["list", "check", "add"], nargs="?", default="check")
    parser.add_argument("--url", default=os.environ.get("CVAT_LOCAL_URL", DEFAULT_URL))
    parser.add_argument("--token")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--task", type=int, action="append", help="task id (repeatable)")
    parser.add_argument("--group", action="append", help="taxonomy group id (repeatable)")
    parser.add_argument("--shape", help="shape for added labels (default: the group's shape)")
    parser.add_argument("--yes", action="store_true", help="apply changes instead of a dry run")
    parser.add_argument("--force", action="store_true", help="allow a group with no model behind it")
    parser.add_argument("--verbose", "-v", action="store_true", help="list the missing label names")
    parser.add_argument("--json", action="store_true", help="machine-readable output for `check`")
    parser.add_argument("--dump", action="store_true", help="print the PATCH payload in a dry run")
    args = parser.parse_args()

    if args.command == "add" and not args.task:
        raise SystemExit("`add` needs --task <id>")

    runtime = build_runtime(load_taxonomy())
    cvat = Cvat(args.url, resolve_token(args))

    handlers = {"list": cmd_list, "check": cmd_check, "add": cmd_add}
    try:
        return handlers[args.command](cvat, runtime, args)
    except CvatError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    sys.exit(main())
