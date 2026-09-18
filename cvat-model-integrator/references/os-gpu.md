# OS, Docker, and GPU guidance

## Linux

Prefer Docker Engine + Compose v2. For NVIDIA GPU, confirm all layers independently:
1. `nvidia-smi` works on host;
2. NVIDIA Container Toolkit is installed;
3. a minimal CUDA container sees the GPU;
4. the chosen model runtime supports the installed driver/CUDA combination;
5. Nuclio deployment requests GPU resources.

Do not debug model code before layer 3 passes.

## Windows

Prefer WSL2 for a Git-cloned CVAT development checkout. Keep the repo in the WSL Linux filesystem rather than `/mnt/c/...` when performance matters. Verify:
- Docker Desktop WSL integration;
- current WSL kernel;
- NVIDIA Windows/WSL driver path if GPU is required;
- `docker compose` from the same WSL environment used for the repo.

Do not mix Windows `nuctl`, WSL paths, and Linux Docker mounts without confirming path translation.

## macOS Intel

Docker Desktop runs Linux containers. CPU paths are usually the least surprising. There is no NVIDIA CUDA path.

## macOS Apple Silicon

Check image architecture. A CVAT/Nuclio image tagged `amd64` may run under emulation but model wheels or native libraries can fail or be slow.

Prefer, in order:
1. arm64-compatible CPU/ONNX runtime inside containers;
2. a host/arm64 sidecar if the model supports it;
3. remote NVIDIA sidecar for GPU-only models.

Do not assume host MPS is available inside a Linux Nuclio container.

## Cross-platform command policy

Prefer:
- Python helper scripts for file/path/base64 operations;
- `docker compose` rather than deprecated `docker-compose` unless the checkout requires it;
- paths derived from the repo instead of hard-coded `/home/...` paths.

Avoid OS-specific one-liners (`base64`, `sed`, `grep`, PowerShell-only syntax) in the reproducible core workflow when a short Python script can do the same job.
