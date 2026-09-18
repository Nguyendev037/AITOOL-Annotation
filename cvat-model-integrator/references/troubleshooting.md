# Troubleshooting

## Function does not appear in CVAT

Check in order:
1. CVAT was started with the serverless Compose overlay;
2. Nuclio container is healthy;
3. deployed function is `ready` in `nuctl get functions --platform local`;
4. `metadata.annotations.type` is valid for the local CVAT parser;
5. `metadata.annotations.spec` is valid JSON, not malformed YAML text;
6. function namespace/project is the one CVAT queries;
7. CVAT server logs for `/api/lambda/functions` errors.

## Function builds but fails at first request

Common causes:
- model file was not copied/downloaded during image build;
- relative working directory differs from local demo;
- native shared library missing (`libgl`, `glib`, etc.);
- CPU-only/GPU wheel mismatch;
- architecture mismatch on arm64;
- checkpoint and code revision mismatch.

Test model initialization inside the built container separately.

## Output is shifted/scaled

Inspect preprocessing transform. Typical causes:
- forgotten inverse letterbox padding;
- width/height swapped;
- normalized coordinates treated as pixels;
- model input coordinates returned without rescaling;
- EXIF orientation mismatch;
- crop offset not restored.

Create a synthetic image with known corners/landmarks to isolate coordinate conversion.

## Skeleton appears but points are wrong

Check:
- keypoint order;
- sublabel order/IDs;
- left/right convention;
- top-level skeleton label;
- `outside` semantics;
- point confidence threshold;
- point coordinates after inverse transform.

Never fix order by visually swapping a few points without comparing the complete model schema.

## Mask is corrupted

Do not send a raw flattened bitmap unless the local contract expects exactly that. Inspect the current built-in mask function or use the matching SDK mask encoder. Verify bbox crop conventions and RLE/compact encoding.

## Works in automatic annotation but not AI Tools

Treat the two paths as separate clients. Inspect current UI handling and required fields. Historical CVAT versions have accepted payloads in one path that fail in another. Reproduce with a minimal result before changing the model.

## GPU OOM

Reduce, in order:
- Nuclio workers/concurrency;
- batch size;
- input resolution only if model allows it;
- precision (FP16/BF16 where supported);
- model size.

Measure memory after warm-up. Do not run multiple workers by default for a large model.

## nuctl version mismatch

Read the Nuclio dashboard image tag from the target checkout's serverless Compose file and install the matching `nuctl`. Never rely on a version copied from an older CVAT tutorial.

## Windows/WSL path failures

Use one execution domain for repo + Docker + scripts. Prefer WSL paths from WSL. Avoid passing Windows backslash paths into Linux containers unless intentionally converted.

## Apple Silicon failures

Check whether failing wheel/image is x86_64-only. Do not interpret emulation failure as a model-code bug. Consider an arm64 sidecar or remote GPU service.
