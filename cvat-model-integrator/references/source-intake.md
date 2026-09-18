# Model source intake

## Contents
1. Required facts
2. GitHub
3. Hugging Face
4. Local weights
5. Model name only
6. Security and licensing

## 1. Required facts

Do not code until these are known or explicitly unresolved:
- official/authoritative source;
- exact model architecture;
- task and output format;
- label/class list;
- keypoint list/order/topology if applicable;
- input preprocessing;
- output decoding/postprocessing;
- checkpoint URL/path and identity;
- dependency/runtime constraints;
- license for code and weights;
- minimum hardware expectations.

## 2. GitHub

Prefer the author's official repo. Record:
- repo URL;
- exact commit SHA or immutable release tag;
- checkpoint release asset and hash when available;
- exact demo/inference entrypoint used as behavioral reference;
- submodules or Git LFS requirements;
- license file at the pinned revision.

Avoid `pip install git+...@main` in a final integration.

## 3. Hugging Face

Record:
- `owner/model`;
- exact revision/commit;
- model card license;
- `config.json` / preprocessor config;
- whether `trust_remote_code=True` is required;
- safetensors/bin/onnx artifact chosen;
- tokenizer/processor version if relevant.

Treat remote custom code as code execution. Inspect it before enabling `trust_remote_code`.

## 4. Local weights

Run `classify_model_source.py` to capture SHA-256. Then find matching architecture/config code.

Do not infer:
- YOLO version from `.pt` alone;
- keypoint order from tensor length alone;
- normalization from model family name alone;
- TensorRT engine portability across GPU/CUDA/TensorRT versions.

If an engine is hardware/runtime-specific, document the build environment and prefer rebuilding from an exchange format when reproducibility matters.

## 5. Model name only

Search primary sources and return a source decision before implementation. If several unrelated models share the same name, ask the user or present the ambiguity.

Selection priority:
1. official author repository/model card;
2. official framework model zoo;
3. author-maintained release;
4. well-maintained wrapper only when necessary.

## 6. Security and licensing

Before building:
- scan install scripts for arbitrary downloads or shell execution;
- avoid embedding API tokens in Docker layers;
- do not commit private model weights;
- record non-commercial/research-only restrictions;
- separate code license from checkpoint/data license;
- record model telemetry/network behavior if relevant.
