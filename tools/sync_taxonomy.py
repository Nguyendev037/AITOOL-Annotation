#!/usr/bin/env python3
"""Generate every derived label artifact from the single source of truth.

``taxonomy.yaml`` is the ONLY file a human edits when the annotation taxonomy
changes. Everything that hardcodes label names, shapes, COCO mappings or
preview colours is generated from it:

    taxonomy.yaml
      -> model-service/taxonomy.json      runtime artifact, baked into the image
                                          and read by handlers/detect.py,
                                          handlers/segment.py and run_results.py
      -> nuclio/functions/*.yaml          only the regions between the
                                          `# >>> GENERATED:<key>` markers
      -> nuclio function env              tools/deploy_nuclio.py injects
                                          TAXONOMY_JSON into each payload

Usage::

    python tools/sync_taxonomy.py --check     # report drift, exit 1 if any
    python tools/sync_taxonomy.py --write     # regenerate all artifacts
    python tools/sync_taxonomy.py --print-spec bbox

Why markers instead of re-dumping the YAML: ``yaml.safe_dump`` would throw away
every explanatory comment in ``nuclio/functions/*.yaml``. Markers let the
hand-written parts (env vars, triggers, build directives) stay hand-written.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_YAML = ROOT / "taxonomy.yaml"
RUNTIME_JSON = ROOT / "model-service" / "taxonomy.json"
FUNCTIONS_DIR = ROOT / "nuclio" / "functions"

#: `cuboid_3d` is not a CVAT 2D shape: it is the LiDAR 3D contract group in
#: `taxonomy.yaml` (mục 7), which declares `supported: false` because no verified
#: 3D model exists yet. It is accepted here so the group can be declared; nothing
#: renders a label spec for it because a group without `function` is never
#: collected as a function-yaml target.
VALID_SHAPES = {"rectangle", "polygon", "polyline", "points", "skeleton", "mask", "cuboid_3d"}
WRAP_WIDTH = 76


# ---------------------------------------------------------------------------
# Loading + validation
# ---------------------------------------------------------------------------

def load_taxonomy(path: Path = TAXONOMY_YAML) -> dict:
    if not path.is_file():
        raise SystemExit(f"taxonomy not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a YAML mapping")
    if not isinstance(data.get("version"), int):
        raise SystemExit("taxonomy.yaml: `version` must be an integer")

    groups = data.get("groups")
    if not isinstance(groups, list) or not groups:
        raise SystemExit("taxonomy.yaml: `groups` must be a non-empty list")

    seen_group_ids: set[str] = set()
    seen_tasks: set[str] = set()
    for group in groups:
        gid = group.get("id")
        if not gid:
            raise SystemExit("taxonomy.yaml: every group needs an `id`")
        if gid in seen_group_ids:
            raise SystemExit(f"taxonomy.yaml: duplicate group id {gid!r}")
        seen_group_ids.add(gid)

        shape = group.get("shape")
        if shape not in VALID_SHAPES:
            raise SystemExit(f"group {gid!r}: shape {shape!r} not in {sorted(VALID_SHAPES)}")

        task = group.get("task")
        if task:
            if task in seen_tasks:
                raise SystemExit(f"taxonomy.yaml: duplicate task {task!r}")
            # A task either runs through a nuclio function here, or declares
            # itself local (chạy tại chỗ trong browser-agent, ví dụ MediaPipe cho
            # pose17/face50). "Local" must be explicit: silently allowing a
            # missing `function` would let a typo drop a GPU task out of
            # deployment without anyone noticing.
            if group.get("local") is True:
                if group.get("function"):
                    raise SystemExit(
                        f"group {gid!r}: `local: true` nhưng vẫn khai `function`; "
                        "model tại chỗ không có nuclio function"
                    )
            elif not group.get("function"):
                raise SystemExit(
                    f"group {gid!r}: `task` set but `function` missing "
                    "(khai `local: true` nếu bài này chạy tại chỗ, không qua nuclio)"
                )
            seen_tasks.add(task)
        elif group.get("supported") is not False:
            raise SystemExit(
                f"group {gid!r}: no `task`, so it must declare `supported: false` "
                "with an `unsupported_reason`"
            )
        if group.get("supported") is False and not group.get("unsupported_reason"):
            raise SystemExit(f"group {gid!r}: `supported: false` requires `unsupported_reason`")

        labels = group.get("labels")
        if not isinstance(labels, list) or not labels:
            raise SystemExit(f"group {gid!r}: `labels` must be a non-empty list")

        names: set[str] = set()
        for label in labels:
            name = label.get("name")
            if not name:
                raise SystemExit(f"group {gid!r}: every label needs a `name`")
            if name in names:
                raise SystemExit(f"group {gid!r}: duplicate label {name!r}")
            names.add(name)
            coco = label.get("coco", [])
            if not isinstance(coco, list):
                raise SystemExit(f"group {gid!r} label {name!r}: `coco` must be a list")
            color = label.get("color")
            if color is not None and (
                not isinstance(color, list)
                or len(color) != 3
                or not all(isinstance(c, int) and 0 <= c <= 255 for c in color)
            ):
                raise SystemExit(
                    f"group {gid!r} label {name!r}: `color` must be [r, g, b] with 0-255 ints"
                )

        # A COCO class may feed only one guideline label per group, otherwise the
        # downstream map would silently pick whichever came last.
        owner: dict[str, str] = {}
        for label in labels:
            for coco in label.get("coco") or []:
                if coco in owner:
                    raise SystemExit(
                        f"group {gid!r}: COCO class {coco!r} is claimed by both "
                        f"{owner[coco]!r} and {label['name']!r}"
                    )
                owner[coco] = label["name"]

    return data


def _oneline(text: str | None) -> str | None:
    """Collapse a folded YAML scalar back to a single line for JSON/env use."""
    if text is None:
        return None
    return " ".join(str(text).split())


# ---------------------------------------------------------------------------
# Runtime artifact
# ---------------------------------------------------------------------------

def build_runtime(taxonomy: dict) -> dict:
    groups_out: list[dict] = []
    tasks: dict[str, dict] = {}
    unsupported: dict[str, dict] = {}

    for group in taxonomy["groups"]:
        labels_out: list[dict] = []
        coco_map: dict[str, str] = {}
        colors: dict[str, list[int]] = {}

        for label in group["labels"]:
            entry: dict = {"name": label["name"]}
            if label.get("coco"):
                entry["coco"] = list(label["coco"])
            if label.get("color"):
                entry["color"] = list(label["color"])
                colors[label["name"]] = list(label["color"])
            if label.get("note"):
                entry["note"] = _oneline(label["note"])
            labels_out.append(entry)
            for coco in label.get("coco") or []:
                coco_map[coco] = label["name"]

        group_out = {
            "id": group["id"],
            "title": group["title"],
            "shape": group["shape"],
            "task": group.get("task"),
            "function": group.get("function"),
            "labels": labels_out,
        }
        if group.get("supported") is False:
            reason = _oneline(group["unsupported_reason"])
            group_out["supported"] = False
            group_out["unsupported_reason"] = reason
            unsupported[group["id"]] = {
                "labels": [label["name"] for label in group["labels"]],
                "shape": group["shape"],
                "reason": reason,
            }
        groups_out.append(group_out)

        if group.get("task"):
            tasks[group["task"]] = {
                "group": group["id"],
                "shape": group["shape"],
                "model_title": _oneline(group.get("model_title")),
                "help_message": _oneline(group.get("help_message")),
                "description": _oneline(group.get("description")),
                # Declared = what the CVAT Models page advertises and what a task
                # should name its labels. coco_map values = what can actually be
                # emitted; a declared label missing from coco_map is advertised
                # but never produced (see `note`).
                "declared": [label["name"] for label in group["labels"]],
                "coco_map": coco_map,
                "colors": colors,
            }

    return {
        "version": taxonomy["version"],
        "generated_by": "tools/sync_taxonomy.py",
        "source_of_truth": "taxonomy.yaml",
        "groups": groups_out,
        "tasks": tasks,
        "unsupported": unsupported,
    }


def render_runtime(runtime: dict) -> str:
    return json.dumps(runtime, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# YAML region rendering
# ---------------------------------------------------------------------------

def render_label_spec(group: dict) -> str:
    """The JSON list CVAT reads from `metadata.annotations.spec`."""
    entries = list(enumerate(label["name"] for label in group["labels"]))
    # Pad the `"name",` field so the `"type"` column lines up, matching the
    # style the files already used by hand.
    width = max(len(json.dumps(name) + ",") for _, name in entries) + 1
    shape = json.dumps(group["shape"])

    lines = ["["]
    for index, (label_id, name) in enumerate(entries):
        trailing = "" if index == len(entries) - 1 else ","
        field = (json.dumps(name) + ",").ljust(width)
        lines.append(f'  {{"id": {label_id:>2}, "name": {field} "type": {shape}}}{trailing}')
    lines.append("]")
    return "\n".join(lines)


def _folded(key: str, value: str) -> str:
    """`key: >-` with wrapped text, dedented (the marker adds indentation)."""
    body = textwrap.fill(
        _oneline(value) or "",
        width=WRAP_WIDTH - 2,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return "\n".join([f"{key}: >-", *(f"  {line}" for line in body.splitlines())])


def _literal(key: str, value: str) -> str:
    """`key: |` with the block indented by two spaces relative to the key."""
    return "\n".join([f"{key}: |", *(f"  {line}" if line else "" for line in value.splitlines())])


def group_regions(group: dict) -> dict[str, str]:
    return {
        "model_title": f"name: {json.dumps(_oneline(group['model_title']))}",
        "help_message": _folded("help_message", group["help_message"]),
        "label_spec": _literal("spec", render_label_spec(group)),
        "description": _folded("description", group["description"]),
    }


def _region_pattern(key: str) -> re.Pattern[str]:
    begin = re.escape(f"# >>> GENERATED:{key}")
    end = re.escape(f"# <<< GENERATED:{key}")
    return re.compile(
        rf"^(?P<ind>[ \t]*){begin}[^\n]*\n(?P<body>.*?)^[ \t]*{end}[^\n]*$",
        re.DOTALL | re.MULTILINE,
    )


def replace_region(text: str, key: str, body: str) -> str:
    match = _region_pattern(key).search(text)
    if match is None:
        raise SystemExit(
            f"missing marker `# >>> GENERATED:{key}` / `# <<< GENERATED:{key}`"
        )
    indent = match.group("ind")
    rendered = "\n".join(
        (indent + line) if line.strip() else "" for line in body.splitlines()
    )
    return text[: match.start("body")] + rendered + "\n" + text[match.end("body") :]


def sync_yaml(path: Path, regions: dict[str, str], write: bool) -> str | None:
    """Return a description of the drift, or None when already in sync."""
    original = path.read_text(encoding="utf-8")
    updated = original
    for key, body in regions.items():
        updated = replace_region(updated, key, body)
    if updated == original:
        return None
    if write:
        path.write_text(updated, encoding="utf-8")
    return f"{path.relative_to(ROOT).as_posix()} (generated regions differ)"


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

def collect_targets(taxonomy: dict, runtime: dict) -> tuple[dict[Path, str], list[tuple[Path, dict]]]:
    files: dict[Path, str] = {RUNTIME_JSON: render_runtime(runtime)}
    yamls: list[tuple[Path, dict]] = []
    for group in taxonomy["groups"]:
        if not group.get("function"):
            continue
        path = FUNCTIONS_DIR / f"{group['task']}.yaml"
        if not path.is_file():
            raise SystemExit(f"group {group['id']!r}: expected function file {path} to exist")
        yamls.append((path, group_regions(group)))
    return files, yamls


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report drift and exit 1 (default)")
    mode.add_argument("--write", action="store_true", help="regenerate all derived artifacts")
    parser.add_argument("--print-spec", metavar="TASK", help="print the CVAT label spec JSON for a task")
    parser.add_argument("--print-runtime", action="store_true", help="print the runtime taxonomy JSON")
    args = parser.parse_args()

    taxonomy = load_taxonomy()
    runtime = build_runtime(taxonomy)

    if args.print_runtime:
        sys.stdout.write(render_runtime(runtime))
        return 0

    if args.print_spec:
        group = next(
            (g for g in taxonomy["groups"] if g.get("task") == args.print_spec), None
        )
        if group is None:
            tasks = [g["task"] for g in taxonomy["groups"] if g.get("task")]
            raise SystemExit(f"unknown task {args.print_spec!r}; available: {', '.join(tasks)}")
        print(render_label_spec(group))
        return 0

    write = args.write
    files, yamls = collect_targets(taxonomy, runtime)
    drift: list[str] = []

    for path, expected in files.items():
        actual = path.read_text(encoding="utf-8") if path.is_file() else None
        if actual == expected:
            continue
        drift.append(f"{path.relative_to(ROOT).as_posix()} ({'missing' if actual is None else 'stale'})")
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")

    for path, regions in yamls:
        found = sync_yaml(path, regions, write)
        if found:
            drift.append(found)

    if not drift:
        print(
            f"taxonomy v{taxonomy['version']} in sync: "
            f"{len(files)} generated file(s), {len(yamls)} function yaml(s), "
            f"{len(runtime['tasks'])} task(s), "
            f"{len(runtime['unsupported'])} unsupported group(s)"
        )
        return 0

    if write:
        print(f"rewrote {len(drift)} target(s):")
        for item in drift:
            print(f"  - {item}")
        print("\nNext: rebuild/redeploy so the running services pick up the change:")
        print("  docker compose up -d --build model-service")
        print("  python tools/deploy_nuclio.py --all")
        print("  powershell -ExecutionPolicy Bypass -File tools/deploy_nuclio.ps1")
        return 0

    print(f"DRIFT: {len(drift)} generated artifact(s) no longer match taxonomy.yaml:")
    for item in drift:
        print(f"  - {item}")
    print("\nRun:  python tools/sync_taxonomy.py --write")
    return 1


if __name__ == "__main__":
    sys.exit(main())
