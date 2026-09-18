# MODEL_INTEGRATION_REPORT

## Summary
- Model:
- Task(s):
- Integration architecture: direct Nuclio / sidecar+Nuclio / SDK batch
- Final status: tested / partial / blocked

## Provenance
- Model source:
- Model revision/tag/commit:
- Checkpoint file:
- Checkpoint SHA-256:
- Code license:
- Weight/model license:

## CVAT target
- Repository:
- Branch:
- Commit:
- Dirty before changes: yes/no
- Serverless Compose file:
- Nuclio dashboard image/version:

## Environment
- OS / architecture:
- Docker:
- Docker Compose:
- CPU:
- GPU / driver / runtime:
- Python/runtime inside model container:

## Annotation contract
- CVAT function kind:
- Output shape types:
- Labels:
- Skeleton/keypoint order (if applicable):
- Confidence/visibility semantics:

## Files changed

## Reproduce
### Start CVAT/serverless

### Build/deploy model

### Smoke invoke

## Verification results
| Test | Expected | Result | Pass? |
|---|---|---|---|
| Function ready | ready | | |
| Single easy image | valid annotation | | |
| Difficult/occluded | valid geometry | | |
| Negative image | no false object / valid empty output | | |
| Multi-instance | correct instances | | |
| Non-default resolution | correct coordinates | | |
| CVAT UI | model visible and usable | | |
| Round trip | type/labels/geometry preserved | | |

## Known limitations

## Troubleshooting notes

## Rollback / uninstall
List only targeted steps for this model/function/service. Do not remove unrelated CVAT data or Docker volumes.
