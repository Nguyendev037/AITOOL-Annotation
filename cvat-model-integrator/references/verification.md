# Verification and acceptance matrix

## Minimum fixture set

Use at least five cases when the task allows:
1. easy positive;
2. difficult/occluded;
3. negative/empty;
4. multiple instances;
5. unusual resolution/aspect ratio.

Add task-specific fixtures:
- segmentation: disconnected component, border-touching object, hole/occlusion policy;
- pose: missing/occluded keypoints, left/right crossing, multiple people;
- tracker: scale/occlusion/reappearance and scene cut;
- classifier/tag: below-threshold case and mutually confusing classes;
- 3D/cuboid: coordinate-frame and calibration edge cases.

## Layered checks

### A. Model-only
- official demo/checkpoint runs;
- deterministic output on fixed fixture within expected tolerance;
- preprocessing verified;
- coordinates restored to source image.

### B. Adapter-only
- JSON serializable;
- finite numeric values;
- no negative/overflow coordinates unless contract allows;
- empty result is valid;
- labels are from declared spec;
- skeleton element names exactly match sublabels.

### C. Nuclio
- build succeeds from clean cache or documented prerequisites;
- function status is ready;
- one direct invocation succeeds;
- logs contain no hidden import/model-load failure;
- restart preserves operation.

### D. CVAT UI/task
- function appears where expected;
- user can select it;
- label mapping works on a task with different internal label IDs;
- annotations land on correct frames;
- threshold changes behavior sensibly;
- no duplicate or malformed objects.

### E. Round trip
Export or read annotations back through the SDK/API and verify:
- object count;
- annotation type;
- labels/sublabels;
- points/mask/cuboid geometry;
- occluded/outside state;
- attributes required by the project.

## Suggested task metrics

Use metrics only when ground truth exists:
- boxes: IoU/mAP or spot-check coordinate error;
- masks: IoU/Dice plus boundary review;
- keypoints: OKS/PCK/pixel error plus visibility agreement;
- tracking: ID switches, fragmentation, temporal drift;
- classification: accuracy/F1/confusion matrix.

Do not use model accuracy metrics as a substitute for integration correctness. A mediocre model can be integrated correctly, and a strong model can be integrated incorrectly.
