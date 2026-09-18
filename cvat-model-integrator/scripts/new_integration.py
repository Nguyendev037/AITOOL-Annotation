#!/usr/bin/env python3
"""Create a conservative CVAT model-integration scaffold.

The scaffold is intentionally model-agnostic. The coding agent must implement and test
model_handler.py before deployment. Uses only the Python standard library.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LABEL_TYPES = {"any", "cuboid", "ellipse", "mask", "points", "polygon", "polyline", "rectangle", "skeleton", "interval", "tag"}
KINDS = {"detector", "interactor", "tracker", "reidentifier"}
MODES = {"direct", "sidecar", "batch"}


def slugify(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not s:
        raise ValueError("slug is empty after normalization")
    return s


def load_labels(path: str | None, default_type: str):
    if not path:
        return [{"id": 0, "name": "object", "type": default_type}]
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "labels" in data:
        data = data["labels"]
    if not isinstance(data, list) or not data:
        raise ValueError("labels JSON must be a non-empty list or {'labels': [...]} object")
    result = []
    for i, item in enumerate(data):
        if not isinstance(item, dict) or not item.get("name"):
            raise ValueError(f"label #{i} must be an object with a name")
        item = dict(item)
        item.setdefault("id", i)
        item.setdefault("type", default_type)
        if item["type"] not in LABEL_TYPES:
            raise ValueError(f"unsupported CVAT label type: {item['type']}")
        result.append(item)
    return result


def yq_scalar(v: str) -> str:
    return "'" + v.replace("'", "''") + "'"


def indent_block(s: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line for line in s.splitlines())


def function_yaml(slug, display_name, kind, labels, framework, mode):
    image = f"cvat.custom.{slug}"
    if kind == "detector":
        spec_json = json.dumps(labels, indent=2, ensure_ascii=False)
        annotations = (
            f"    name: {yq_scalar(display_name)}\n"
            "    type: detector\n"
            "    spec: |\n"
            f"{indent_block(spec_json, 6)}"
        )
    elif kind == "interactor":
        annotations = (
            f"    name: {yq_scalar(display_name)}\n"
            "    version: 2\n"
            "    type: interactor\n"
            "    spec:\n"
            "    min_pos_points: 0\n"
            "    min_neg_points: 0\n"
            "    startswith_box_optional: true"
        )
    else:
        annotations = f"    name: {yq_scalar(display_name)}\n    type: {kind}\n    spec:"

    extra = ""
    if mode == "sidecar":
        extra = "\n        - kind: RUN\n          value: pip install --no-cache-dir requests"
    return f"""metadata:
  name: custom-{slug}
  namespace: cvat
  annotations:
{annotations}
spec:
  description: {yq_scalar('Custom CVAT integration for ' + display_name + ' (' + framework + ', ' + mode + ')')}
  runtime: 'python:3.10'
  handler: main:handler
  eventTimeout: 60s
  build:
    image: {image}
    baseImage: python:3.10-slim
    directives:
      preCopy:
        - kind: RUN
          value: apt-get update && apt-get install --no-install-recommends -y libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
        - kind: WORKDIR
          value: /opt/nuclio
        - kind: RUN
          value: pip install --no-cache-dir pillow numpy{extra}
  triggers:
    myHttpTrigger:
      numWorkers: 1
      kind: 'http'
      workerAvailabilityTimeoutMilliseconds: 10000
      attributes:
        maxRequestBodySize: 33554432
  platform:
    attributes:
      restartPolicy:
        name: always
        maximumRetryCount: 3
      mountMode: volume
"""


DETECTOR_MAIN_PY = '''import base64
import io
import json
from PIL import Image
from model_handler import ModelHandler


def init_context(context):
    context.logger.info("Init context... 0%")
    context.user_data.model = ModelHandler()
    context.logger.info("Init context... 100%")


def handler(context, event):
    data = event.body
    if not isinstance(data, dict) or "image" not in data:
        return context.Response(body=json.dumps({"error": "missing image"}), content_type="application/json", status_code=400)

    image = Image.open(io.BytesIO(base64.b64decode(data["image"]))).convert("RGB")
    threshold = float(data.get("threshold", 0.5))
    results = context.user_data.model.infer(image=image, threshold=threshold, request=data)
    if not isinstance(results, (list, dict)):
        raise TypeError("ModelHandler.infer() must return a JSON-serializable list or dict matching the local CVAT function contract")
    return context.Response(body=json.dumps(results), headers={}, content_type="application/json", status_code=200)
'''

GENERIC_MAIN_PY = '''import json
from model_handler import ModelHandler


def init_context(context):
    context.logger.info("Init context... 0%")
    context.user_data.model = ModelHandler()
    context.logger.info("Init context... 100%")


def handler(context, event):
    # Interactor/tracker/reidentifier request contracts differ by function kind and CVAT revision.
    # Inspect the closest built-in function in THIS checkout and implement ModelHandler.handle accordingly.
    result = context.user_data.model.handle(event.body)
    return context.Response(body=json.dumps(result), headers={}, content_type="application/json", status_code=200)
'''

DIRECT_HANDLER = '''class ModelHandler:
    def __init__(self):
        # TODO: load the pinned model/checkpoint once here. Do not download on every request.
        raise NotImplementedError("Implement model initialization")

    def infer(self, image, threshold, request):
        # Detector path. TODO: preprocess -> infer -> postprocess -> CVAT payload.
        raise NotImplementedError("Implement detector inference")

    def handle(self, request):
        # Interactor/tracker/reidentifier path. Mirror the closest built-in function in THIS checkout.
        raise NotImplementedError("Implement function-kind request contract")
'''

SIDECAR_HANDLER = '''import os
import base64
import io
import requests


class ModelHandler:
    def __init__(self):
        self.url = os.environ.get("MODEL_SERVER_URL", "http://host.docker.internal:9000/infer")
        self.timeout = float(os.environ.get("MODEL_SERVER_TIMEOUT", "60"))

    def _post(self, payload):
        response = requests.post(self.url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def infer(self, image, threshold, request):
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        payload = dict(request) if isinstance(request, dict) else {}
        payload["image"] = base64.b64encode(buf.getvalue()).decode("ascii")
        payload["threshold"] = threshold
        return self._post(payload)

    def handle(self, request):
        return self._post(request)
'''

BATCH_PY = '''"""Batch fallback for CVAT annotation kinds not exposed by the current Nuclio/UI contract.

Implement this with cvat-sdk pinned to the CVAT checkout/release you are targeting.
The runner should perform inference, construct exact CVAT annotation models, upload them,
and verify a round-trip read. Do not silently approximate geometry types.
"""

raise SystemExit("TODO: implement model-specific batch annotation runner after inspecting the local CVAT SDK version")
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--display-name")
    ap.add_argument("--kind", choices=sorted(KINDS), default="detector")
    ap.add_argument("--shape", choices=sorted(LABEL_TYPES), default="rectangle")
    ap.add_argument("--labels-json")
    ap.add_argument("--framework", default="custom")
    ap.add_argument("--mode", choices=sorted(MODES), default="direct")
    ap.add_argument("--source", default="")
    ap.add_argument("--revision", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not (repo / "docker-compose.yml").exists() or not (repo / "serverless").exists():
        raise SystemExit(f"Not a recognized Git-cloned CVAT root: {repo}")

    slug = slugify(args.slug)
    display = args.display_name or slug.replace("-", " ").title()
    labels = load_labels(args.labels_json, args.shape)

    if args.mode == "batch":
        out = repo / "tools" / "cvat-model-integrations" / slug
    else:
        out = repo / "serverless" / "custom" / slug / "nuclio"
    if out.exists() and any(out.iterdir()) and not args.force:
        raise SystemExit(f"Refusing to overwrite non-empty directory: {out}. Use --force only after review.")
    out.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": display,
        "slug": slug,
        "integration_mode": args.mode,
        "function_kind": args.kind,
        "default_shape_type": args.shape,
        "framework": args.framework,
        "model_source": args.source,
        "model_revision": args.revision,
        "labels": labels,
        "status": "scaffolded-not-tested",
    }
    (out / "model_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "README.md").write_text(
        f"# {display}\n\nGenerated scaffold. Implement, test, and document this integration before deployment.\n",
        encoding="utf-8",
    )
    if args.mode == "batch":
        (out / "batch_auto_annotate.py").write_text(BATCH_PY, encoding="utf-8")
    else:
        (out / "function.yaml").write_text(function_yaml(slug, display, args.kind, labels, args.framework, args.mode), encoding="utf-8")
        (out / "main.py").write_text(DETECTOR_MAIN_PY if args.kind == "detector" else GENERIC_MAIN_PY, encoding="utf-8")
        (out / "model_handler.py").write_text(SIDECAR_HANDLER if args.mode == "sidecar" else DIRECT_HANDLER, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
