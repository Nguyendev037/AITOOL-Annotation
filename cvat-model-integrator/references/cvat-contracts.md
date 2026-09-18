# CVAT contracts and local-source-of-truth rules

## Contents
1. Local checkout wins
2. Current public reference points
3. Nuclio detector payloads
4. Skeletons
5. Masks
6. Interactors and trackers
7. Labels and mapping

## 1. Local checkout wins

Before implementing any adapter, inspect:
- `components/serverless/docker-compose.serverless.yml` or its current equivalent;
- `serverless/**/nuclio/function.yaml` examples closest to the task;
- their `main.py` and `model_handler.py`;
- server-side lambda/serverless parsing code when using an uncommon geometry;
- UI model handling when a model works in batch but fails in AI Tools.

Do not use this reference as an ABI specification.

## 2. Current public reference points

Useful official pages as of 2026-09:
- CVAT repository: https://github.com/cvat-ai/cvat
- Serverless/automatic annotation install: https://docs.cvat.ai/docs/administration/community/advanced/installation_automatic_annotation/
- Serverless tutorial: https://docs.cvat.ai/docs/manual/advanced/serverless-tutorial/
- AI models: https://docs.cvat.ai/docs/annotation/auto-annotation/ai-models/
- Auto-annotation SDK: https://docs.cvat.ai/docs/api_sdk/sdk/auto-annotation/
- Shape types: https://docs.cvat.ai/docs/annotation/manual-annotation/shapes/

CVAT Community's public docs describe Nuclio as the model deployment route. Native/agent functions are edition-dependent; do not assume they are available in a Community clone.

## 3. Nuclio detector payloads

Common built-in detector examples return a JSON list. A rectangle result commonly resembles:

```json
{
  "confidence": "0.93",
  "label": "person",
  "points": [x1, y1, x2, y2],
  "type": "rectangle"
}
```

Polygon, mask, and skeleton payloads have different structures. Copy the current built-in example for the target task instead of generalizing from rectangles.

Do not assume arbitrary extra fields survive parsing. Historical CVAT issues show that rotation and attributes have differed across paths/versions.

## 4. Skeletons

A skeleton label spec normally includes:
- top-level label name and `type: skeleton`;
- SVG topology;
- ordered `sublabels`, each typically `type: points`;
- stable IDs within the spec.

Inference normally returns a top-level skeleton object with `elements`, each element containing the corresponding point label and coordinates. Inspect the current whole-body pose function in the local checkout.

Validate:
- model point order == CVAT sublabel order;
- left/right convention;
- original-pixel coordinates after resize/letterbox reversal;
- missing point semantics (`outside`, occlusion, or version-specific representation);
- all SVG `data-label-name` entries match sublabels.

## 5. Masks

CVAT uses a compact mask representation rather than accepting an arbitrary NumPy array. For SDK auto-annotation, the official API exposes `cvat_sdk.masks.encode_mask`. Legacy Nuclio functions may use a serverless-specific encoded list. Mirror the current checkout.

Test:
- one connected component;
- multiple disconnected components;
- mask at image border;
- small object;
- empty mask;
- overlap with another instance;
- holes if the target annotation policy requires them.

## 6. Interactors and trackers

Interactors accept prompts and currently may have UI restrictions on returned shape type. Inspect current docs/UI before promising polygon or skeleton interactive output.

Trackers maintain state across frames. Test one agent/function instance first; concurrent state handling is model and CVAT-version sensitive.

## 7. Labels and mapping

Use label **names and explicit specs** as the stable mapping layer. Do not assume task label IDs match function/model class IDs.

For a model with labels `[person, car]` and a task whose internal IDs are different, the adapter/CVAT mapping must still produce the correct semantic label by name/spec.

For skeletons, this rule applies recursively to sublabels.
