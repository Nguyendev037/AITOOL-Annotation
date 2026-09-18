# Integration architecture

## Contents
1. Decision tree
2. Direct Nuclio
3. Sidecar + Nuclio
4. SDK/REST batch fallback
5. Geometry coverage policy

## 1. Decision tree

Choose the least complex architecture that preserves the model's true output.

1. Does the target CVAT checkout's Nuclio/serverless path accept the required function kind and geometry?
   - Yes -> continue.
   - No/unclear -> inspect local parser/UI code. If still unsupported, use SDK/REST batch.
2. Can the model and dependencies live reliably inside one Nuclio container?
   - Yes -> direct Nuclio.
   - No -> sidecar inference service + thin Nuclio adapter.
3. Does the user require interactive AI Tools?
   - Yes -> direct/sidecar Nuclio is required for CVAT Community where supported.
   - No -> SDK/REST batch can be simpler and more faithful.

## 2. Direct Nuclio

Use for compact PyTorch/ONNX/OpenVINO/TensorFlow/custom runtimes with manageable dependency graphs.

Keep these layers separate:
- `main.py`: CVAT/Nuclio request/response adapter only.
- `model_handler.py`: load, preprocess, infer, postprocess.
- `function.yaml`: runtime, image build, labels/spec, triggers.
- `model_manifest.json`: provenance and test state.

Load the model once in `init_context`. Do not clone repositories or download checkpoints per request.

## 3. Sidecar + Nuclio

Use when:
- the model repo has a complex server/runtime;
- CUDA/Python versions conflict with Nuclio examples;
- the model uses TensorRT/Triton/vLLM-like service patterns;
- weights are very large;
- multiple CVAT functions should share one model process;
- host-specific acceleration must be isolated.

Architecture:

```text
CVAT -> Nuclio thin adapter -> internal model service -> model
                    <- normalized CVAT payload <-
```

Requirements:
- health endpoint;
- bounded request timeout;
- deterministic response schema;
- no public port unless required;
- pinned sidecar image/dependencies;
- readiness check before declaring the model available;
- no credentials baked into images.

On Docker Desktop, `host.docker.internal` can be useful, but prefer a shared Compose network when practical. On Linux, verify the actual routing rather than assuming Desktop behavior.

## 4. SDK/REST batch fallback

Use when a current CVAT Community Nuclio path cannot faithfully emit the required annotation kind.

The runner should:
1. authenticate to local CVAT;
2. read task/project labels and IDs;
3. download/iterate frames through supported APIs;
4. run model inference;
5. construct the exact CVAT annotation type;
6. upload annotations in bounded batches;
7. read annotations back;
8. compare count/type/coordinates/attributes;
9. leave a dry-run mode.

Pin `cvat-sdk` to a version compatible with the target CVAT checkout/release. If the checkout itself provides the SDK package, prefer installing from that checkout or its matching release.

## 5. Geometry coverage policy

CVAT's general label/shape vocabulary is broader than the geometry exposed by every AI integration path. As of the 2026 public API docs, shape vocabulary includes rectangle, polygon, polyline, points, ellipse, cuboid, mask, and skeleton; label vocabulary also includes tag and interval. Direct serverless/UI support can be narrower and version-dependent.

Use this policy:

| Required output | Preferred path | Fallback |
|---|---|---|
| rectangle/bbox | detector Nuclio | SDK batch |
| polygon | detector Nuclio if local parser confirms | SDK batch |
| mask / instance segmentation | detector or interactor Nuclio | SDK batch |
| skeleton / keypoints | detector Nuclio | SDK batch |
| free points | detector if local parser/UI confirms | SDK batch |
| tracking | tracker Nuclio if current checkout supports shape | batch track upload |
| re-identification | reidentifier/serverless path if present | batch association |
| polyline | direct only if local contract confirms | SDK batch |
| ellipse | direct only if local contract confirms | SDK batch |
| cuboid / 3D shape | direct only if current task/UI contract confirms | SDK batch/custom import |
| tag / classification | direct only if local serverless path confirms | SDK batch |
| interval / timeline event | SDK/REST batch unless current checkout explicitly supports model output | SDK batch |

Never change a cuboid to a rectangle, interval to a tag, or disconnected mask to a single polygon merely to fit a narrower integration path unless the user explicitly accepts that loss.
