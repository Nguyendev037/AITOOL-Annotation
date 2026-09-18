---
name: cvat-model-integrator
description: Integrate a pretrained or custom computer-vision model into a local CVAT Community checkout cloned from GitHub and run with Docker Compose. Use when a coding agent must add, update, debug, or validate a CVAT model from a GitHub repo, Hugging Face repo, local checkpoint/model directory, URL, or model name. Support detection, segmentation, keypoints/skeletons, points, classification/tags, tracking, re-identification, polylines, ellipses, cuboids/3D-related outputs, intervals, and other CVAT label geometries by choosing a direct Nuclio, sidecar+Nuclio, or CVAT SDK batch path. Target Linux, macOS, Windows+WSL2, CPU, NVIDIA GPU, and Apple Silicon without hard-coding one CVAT/Nuclio version.
---

# CVAT Model Integrator

Integrate one model into the user's **existing Git-cloned CVAT repository** and leave a reproducible, tested implementation. Treat the local checkout as the source of truth. Never assume that commands, paths, Nuclio versions, response payloads, or UI capabilities from an older CVAT release still apply.

## Non-negotiable rules

1. **Inspect before editing.** Run `scripts/probe_cvat_env.py` first from or against the CVAT repo.
2. **Preserve the user's checkout.** Do not reset, clean, rebase, delete, or overwrite unrelated changes. Record the starting branch/commit and dirty state.
3. **Use the local CVAT contract.** Inspect the closest built-in function under `serverless/**/nuclio` and current local server/API code before implementing a payload. Bundled references are guidance, not an ABI guarantee.
4. **Pin model inputs.** Record exact Git commit/tag/Hugging Face revision/checkpoint SHA-256 whenever possible. Never build a reproducible integration around a floating `main`, `latest`, or mutable URL if a pin exists.
5. **Do not guess model architecture from a checkpoint extension.** A `.pt`, `.pth`, `.onnx`, `.engine`, or `.ckpt` file is not enough to infer preprocessing, labels, keypoint order, output decoding, or license.
6. **Do not approximate annotation geometry silently.** If the target CVAT revision cannot consume a model's native output in the AI UI, use the SDK/batch fallback and preserve the true geometry instead of converting it to an unrelated shape.
7. **Test end-to-end.** A successful Docker build is not completion. Verify inference, returned geometry, CVAT visibility, label mapping, and at least one annotation round trip.
8. **Never expose Nuclio dashboard publicly.** If debugging requires publishing port 8070, bind it to loopback only.
9. **Do not mark the integration tested until it is tested.** Keep `model_manifest.json.status` honest.
10. **Do not promise universal success.** If a model has incompatible licensing, unavailable weights, unsupported hardware, missing architecture code, or a CVAT limitation, report the blocker and implement the strongest non-lossy fallback that the user accepts.

## Workflow

### 1. Establish the repository and environment

Run:

```bash
python <skill>/scripts/probe_cvat_env.py --repo <CVAT_REPO> --json
```

Use the result to determine:
- OS and architecture;
- native Windows vs WSL2;
- Docker and Compose availability;
- repository branch, commit, and dirty state;
- serverless Compose file path;
- Nuclio dashboard image and version declared by this checkout;
- `nuctl` availability;
- NVIDIA GPU visibility.

If Docker is not healthy, stop integration work at the environment stage. Do not compensate by rewriting CVAT.

Read `references/os-gpu.md` when host/container/GPU behavior matters.

### 2. Resolve and inspect the model source

Run:

```bash
python <skill>/scripts/classify_model_source.py '<MODEL_SOURCE>' [--revision <PIN>]
```

Then inspect the actual source:
- **GitHub:** official repository, model config, inference/demo path, releases/checkpoints, dependency versions, license.
- **Hugging Face:** model card, exact revision, config/preprocessor files, custom code requirements, weight files, license.
- **Local file/directory:** compute checksum; find architecture/config/preprocessing code. Ask for missing architecture details rather than guessing.
- **Model name only:** locate the official or author-maintained implementation and pretrained weights. Prefer primary sources over wrappers.
- **Remote HTTP inference endpoint:** treat it as a sidecar/provider source and document authentication, schema, timeout, and data handling.

Determine and record:
- task(s);
- output geometry;
- class names and exact order;
- keypoint/sublabel names and exact order;
- input size, color order, normalization and resize/letterbox behavior;
- confidence semantics;
- NMS/postprocessing;
- CPU/GPU requirements;
- model and code license;
- exact checkpoint identity.

Read `references/source-intake.md` for the full intake checklist.

### 3. Map model outputs to CVAT labels before coding

Identify the required CVAT annotation kinds. CVAT label types may include `rectangle`, `polygon`, `mask`, `points`, `skeleton`, `polyline`, `ellipse`, `cuboid`, `tag`, `interval`, and version-specific additions.

For skeletons, obtain the real point order and skeleton topology from the model or project specification. Never invent or reorder landmarks. Ensure the CVAT skeleton label spec and the model output order agree exactly.

Read `references/cvat-contracts.md` and inspect the local checkout. The local checkout wins on conflicts.

### 4. Select the integration architecture

Use this order:

**A. Direct Nuclio function — preferred**
- Use when dependencies fit cleanly in a Nuclio container and the local CVAT serverless path supports the desired function kind/output.
- Best for ordinary detectors, masks/polygons, pose/skeletons, interactors, and trackers.

**B. Sidecar inference service + thin Nuclio adapter — preferred fallback**
- Use when model dependencies are large/conflicting, require a dedicated runtime/server, require special CUDA packages, or should not be rebuilt into Nuclio.
- Keep the CVAT-visible Nuclio function small. Let it translate CVAT requests to the sidecar and translate sidecar responses back.
- Keep the sidecar on the Docker/internal host network; do not expose it unnecessarily.

**C. CVAT SDK/REST batch annotation — non-lossy coverage fallback**
- Use when the current Community/Nuclio/UI path does not support the required output geometry or workflow, especially unusual shapes, tags, intervals, or version-specific types.
- This path may not make the model appear as an interactive AI Tool. State that limitation clearly.
- Preserve the true CVAT annotation type and verify a round-trip read.

Read `references/architecture.md` before choosing B or C.

### 5. Scaffold conservatively

For a direct integration:

```bash
python <skill>/scripts/new_integration.py \
  --repo <CVAT_REPO> \
  --slug <MODEL_SLUG> \
  --display-name '<DISPLAY_NAME>' \
  --kind detector \
  --shape rectangle \
  --framework <FRAMEWORK> \
  --mode direct \
  --source '<SOURCE>' \
  --revision '<PIN>' \
  [--labels-json <LABELS_JSON>]
```

For a sidecar adapter, use `--mode sidecar`. For a non-lossy batch fallback, use `--mode batch`.

The scaffold is **not a finished integration**. Replace its placeholder handler with model-specific code and adapt `function.yaml` to the conventions of the target checkout.

Prefer a location that matches the current repository's organization. `serverless/custom/<slug>/nuclio` is a safe default for isolated custom work; if the project has an established custom-model location, follow it instead.

### 6. Implement preprocessing and inference faithfully

Mirror the model's official preprocessing exactly unless there is a documented reason not to:
- RGB vs BGR;
- EXIF/orientation handling;
- resize/letterbox/crop;
- normalization;
- tensor layout and dtype;
- device placement and precision;
- confidence threshold;
- NMS;
- output coordinate transform back to original pixels.

Load heavyweight model state once during function initialization, not on every request.

Do not download mutable weights on every inference request. Prefer build-time download of pinned artifacts, a versioned mounted cache, or a sidecar image with the pinned model baked in.

### 7. Implement the CVAT adapter from the current contract

Before writing the final response payload:
1. Find the closest built-in function in the current checkout by task and framework.
2. Inspect its `function.yaml`, `main.py`, and `model_handler.py`.
3. Inspect local server parsing code if the desired geometry is not represented by an example.
4. Reproduce the required field names and numeric conventions exactly.
5. Add only fields confirmed by the current contract; do not assume unsupported fields such as rotation or arbitrary attributes will survive serverless parsing.

For skeletons, verify all of:
- top-level skeleton label;
- sublabel IDs/names;
- `elements` order;
- `outside`/occlusion semantics;
- SVG `data-label-name` values;
- point coordinates in original-image pixels.

For masks, use the encoding expected by the current checkout. Test disconnected components and holes if the model can emit them.

### 8. Match the Nuclio version to this checkout

Use the version found in `components/serverless/docker-compose.serverless.yml` (or the current equivalent). Do not copy a version from this skill or an old tutorial.

Start CVAT with the serverless Compose overlay specified by this checkout. The typical Community pattern is:

```bash
docker compose -f docker-compose.yml -f components/serverless/docker-compose.serverless.yml up -d
```

Add `--build` only when needed. If the checkout includes a dev overlay or custom deployment files, preserve the user's existing Compose stack.

Deploy using the checkout's current CPU/GPU helper scripts when available. If deploying directly with `nuctl`, derive the arguments from current built-in functions and current Nuclio version.

### 9. Validate statically before build/deploy

Run:

```bash
python <skill>/scripts/validate_integration.py <INTEGRATION_DIR>
```

Fix all errors. Treat warnings as review items, especially warnings about annotation types that may require the SDK fallback.

### 10. Build and deploy

Use the least invasive path supported by the local checkout.

For CPU, prefer the repository's current deployment helper if present. For NVIDIA GPU:
- verify Docker sees the GPU first;
- verify NVIDIA Container Toolkit/WSL GPU support;
- request only the GPU resources needed;
- keep worker count conservative until VRAM use is measured.

For macOS/Apple Silicon, do not assume CUDA. Prefer CPU, Metal only when the chosen model/runtime actually supports it inside the chosen architecture, or a sidecar designed for the host. Nuclio containers are Linux containers; host-native MPS code does not automatically work inside them.

### 11. Smoke-test the function independently

For Nuclio functions, run:

```bash
python <skill>/scripts/smoke_invoke.py <FUNCTION_NAME> <TEST_IMAGE> --threshold 0.5
```

Also inspect:
- `nuctl get functions --platform local`;
- function/container logs;
- returned JSON;
- coordinate bounds;
- class/sublabel names;
- empty-result behavior;
- malformed-request behavior.

Do not proceed to CVAT UI testing while the function itself is unhealthy.

### 12. Verify in CVAT end-to-end

Verify all applicable paths:
- model appears in the expected AI/Automatic Annotation UI;
- single-frame inference;
- automatic annotation over multiple frames/images;
- task label mapping;
- threshold control;
- segmentation geometry and disconnected components;
- keypoint/skeleton visibility/occlusion;
- tracking initialization and subsequent frames;
- no cross-instance keypoint mixing;
- correct behavior on no-detection frames;
- output after export and re-import when the downstream format matters.

Use at least:
1. an easy positive image;
2. a difficult/occluded image;
3. a negative image;
4. a multi-instance image if applicable;
5. a non-default image size/aspect ratio.

Read `references/verification.md` for the acceptance matrix.

### 13. Debug by layer, not by random edits

Classify failures into:
1. model source/weights;
2. Python/dependency/runtime;
3. preprocessing/postprocessing;
4. Nuclio build/startup;
5. request/response contract;
6. CVAT label mapping;
7. CVAT UI capability;
8. hardware/container access.

Read `references/troubleshooting.md`. Preserve the first failing payload/log before changing code.

### 14. Finish reproducibly

Update `model_manifest.json` with:
- exact model source and revision/checksum;
- CVAT branch/commit;
- Nuclio version;
- framework/runtime/dependency pins;
- CPU/GPU target;
- label and sublabel mapping;
- deployment command;
- smoke-test command;
- known limitations;
- `status: "tested"` only after end-to-end verification.

Create `MODEL_INTEGRATION_REPORT.md` using `assets/MODEL_INTEGRATION_REPORT.template.md`.

Include rollback/uninstall instructions that remove only the added function/service/files. Never suggest deleting the user's whole CVAT deployment or Docker volumes as a normal rollback.

## Completion criteria

Do not call the task complete until all applicable items are true:
- source and weights are pinned or checksummed;
- license and usage restrictions are recorded;
- CVAT checkout/commit is recorded;
- model builds or sidecar runs;
- serverless function reaches ready state when used;
- independent invocation succeeds;
- model is visible in the expected CVAT UI when direct UI integration is claimed;
- predicted annotation geometry is correct on real test images;
- label/sublabel mapping is correct;
- export/re-import or SDK round trip preserves required geometry;
- install/deploy steps are reproducible from a clean clone of the same CVAT revision;
- rollback is documented;
- report and manifest are updated.

## Expected final response to the user

Summarize:
- integration architecture used;
- files added/changed;
- exact model/checkpoint revision;
- CVAT commit tested;
- deploy command;
- test result by annotation type;
- hardware used;
- known limitations;
- rollback command/steps;
- path to `MODEL_INTEGRATION_REPORT.md`.

Do not hide partial failures behind a generic “installed successfully” message.
