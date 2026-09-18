#!/usr/bin/env python3
"""Generate nuclio function payloads for the CVAT serverless functions.

The nuclio dashboard is not published on the host (port 8070 is only reachable
on the ``cvat_cvat`` docker network), so deployment is done by POSTing the
generated JSON to the dashboard REST API from a throwaway container:

    python tools/deploy_nuclio.py --all
    powershell -File tools/deploy_nuclio.ps1

What this script does
---------------------
1. Reads ``nuclio/functions/<name>.yaml``.
2. Inlines ``nuclio/src/main.py`` as ``spec.build.functionSourceCode``
   (base64), which is how nuclio accepts single-file source deploys.
3. Writes ``nuclio/build/<name>.json`` ready for ``POST /api/functions``.

Options let you deploy the same code under a second name with a different
``LABEL_MAP``, which is how a function is aligned to the label names of a
specific CVAT task without editing YAML.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_taxonomy import build_runtime, load_taxonomy  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
FUNCTIONS_DIR = REPO_ROOT / "nuclio" / "functions"
SOURCE_FILE = REPO_ROOT / "nuclio" / "src" / "main.py"
BUILD_DIR = REPO_ROOT / "nuclio" / "build"


def available_functions() -> list[str]:
    return sorted(path.stem for path in FUNCTIONS_DIR.glob("*.yaml"))


def _set_env(spec: dict, name: str, value: str) -> None:
    for entry in spec.setdefault("env", []):
        if entry.get("name") == name:
            entry["value"] = value
            return
    spec["env"].append({"name": name, "value": value})


def task_taxonomy(task: str) -> str:
    """Compact JSON taxonomy for one task, straight from `taxonomy.yaml`.

    `nuclio/src/main.py` refuses to start without this, which is what keeps the
    function's label mapping from drifting away from the single source of truth.
    """
    runtime = build_runtime(load_taxonomy())
    entry = runtime["tasks"].get(task)
    if entry is None:
        tasks = ", ".join(sorted(runtime["tasks"])) or "none"
        raise SystemExit(
            f"taxonomy.yaml declares no task {task!r} (needed by "
            f"nuclio/functions/{task}.yaml); declared tasks: {tasks}"
        )
    return json.dumps(
        {"declared": entry["declared"], "coco_map": entry["coco_map"]},
        separators=(",", ":"),
        ensure_ascii=False,
    )


def build_payload(
    name: str,
    source_code: str,
    label_map: str | None = None,
    rename_to: str | None = None,
    image_suffix: str | None = None,
) -> dict:
    config_path = FUNCTIONS_DIR / f"{name}.yaml"
    if not config_path.is_file():
        raise SystemExit(f"unknown function {name!r}; available: {', '.join(available_functions())}")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    metadata = config.setdefault("metadata", {})
    spec = config.setdefault("spec", {})

    if rename_to:
        metadata["name"] = rename_to
        metadata.setdefault("annotations", {})["name"] = (
            f"{metadata.get('annotations', {}).get('name', name)} [{rename_to}]"
        )

    if image_suffix:
        build = spec.setdefault("build", {})
        build["image"] = f"{build.get('image', name)}-{image_suffix}"

    if label_map is not None:
        # Validate before shipping it into the function environment.
        try:
            parsed = json.loads(label_map)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"--label-map is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SystemExit("--label-map must be a JSON object")
        _set_env(spec, "LABEL_MAP", json.dumps(parsed, separators=(",", ":")))

    # Inject the taxonomy (COCO map + declared labels) from taxonomy.yaml, so
    # nuclio/src/main.py never hardcodes a class name.
    task = next(
        (entry.get("value") for entry in spec.get("env", []) if entry.get("name") == "TASK"),
        None,
    )
    if not task:
        raise SystemExit(f"{config_path.name}: no TASK env entry; cannot resolve the taxonomy")
    _set_env(spec, "TAXONOMY_JSON", task_taxonomy(str(task).strip().lower()))

    spec.setdefault("build", {})["functionSourceCode"] = base64.b64encode(
        source_code.encode("utf-8")
    ).decode("ascii")
    return config


MANIFEST_FILE = BUILD_DIR / "manifest.json"


def update_manifest(written: list[str]) -> list[str]:
    """Record which payload files are real function payloads.

    `nuclio/build/` is a scratch directory: it also collects request fixtures and
    ad-hoc dumps. `tools/deploy_nuclio.ps1` used to glob every `*.json` in it and
    then tried to POST fixtures as functions ("Function name must be provided in
    metadata"). The manifest is the explicit contract between the two tools.

    Entries accumulate across runs so `--function bbox --rename-to X` does not
    drop the payloads generated earlier, and vanished files are pruned.
    """
    previous: list[str] = []
    if MANIFEST_FILE.is_file():
        try:
            previous = json.loads(MANIFEST_FILE.read_text(encoding="utf-8")).get("functions", [])
        except (json.JSONDecodeError, AttributeError):
            previous = []

    names = sorted(
        name for name in {*previous, *written} if (BUILD_DIR / f"{name}.json").is_file()
    )
    MANIFEST_FILE.write_text(
        json.dumps(
            {"generated_by": "tools/deploy_nuclio.py", "functions": names}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--function", action="append", default=[], help="function name (repeatable)")
    parser.add_argument("--all", action="store_true", help="generate every function in nuclio/functions")
    parser.add_argument("--label-map", help='JSON object renaming labels, e.g. \'{"pedestrian":"person"}\'')
    parser.add_argument(
        "--label-map-file",
        help="path to a JSON file with the label map; use this on Windows to avoid shell quoting problems",
    )
    parser.add_argument("--rename-to", help="deploy under a different nuclio function name")
    parser.add_argument("--image-suffix", help="suffix appended to the built docker image tag")
    args = parser.parse_args()

    names = available_functions() if args.all or not args.function else args.function
    if not names:
        raise SystemExit(f"no functions found in {FUNCTIONS_DIR}")

    if args.label_map and args.label_map_file:
        raise SystemExit("use either --label-map or --label-map-file, not both")

    label_map = args.label_map
    if args.label_map_file:
        map_path = Path(args.label_map_file)
        if not map_path.is_absolute():
            map_path = REPO_ROOT / map_path
        if not map_path.is_file():
            raise SystemExit(f"label map file not found: {map_path}")
        label_map = map_path.read_text(encoding="utf-8")

    if (args.rename_to or label_map or args.image_suffix) and len(names) > 1:
        raise SystemExit("--rename-to/--label-map/--image-suffix only apply to a single --function")

    source_code = SOURCE_FILE.read_text(encoding="utf-8")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    written = []
    for name in names:
        payload = build_payload(
            name,
            source_code,
            label_map=label_map,
            rename_to=args.rename_to,
            image_suffix=args.image_suffix,
        )
        out_path = BUILD_DIR / f"{payload['metadata']['name']}.json"
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(out_path)
        print(f"wrote {out_path.relative_to(REPO_ROOT)}  ({out_path.stat().st_size} bytes)")

    manifest = update_manifest([path.stem for path in written])
    print(f"\nmanifest: {', '.join(manifest)}")
    print("Deploy with:  powershell -File tools/deploy_nuclio.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
