"""Prove whether a heavy model-service request blocks the asyncio event loop.

`model-service/app.py` deliberately declares its inference endpoints as plain
`def` so FastAPI runs them in Starlette's threadpool.  If someone changes one
back to `async def`, the blocking torch/ultralytics call runs *on* the event
loop and freezes every other request in the process.  This script detects that
regression: it saturates one endpoint and measures `/health` latency at the same
time.  A free event loop keeps `/health` near its idle baseline; a blocked one
makes it wait behind the in-flight inference.

Usage:
    python tools/bench_event_loop.py --image work/job_1573/frame_25/original.jpg
    python tools/bench_event_loop.py --image <jpg> --endpoint /segment-lane --concurrency 8

Stdlib only, so it runs on the host without installing anything.
"""
from __future__ import annotations

import argparse
import statistics
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BOUNDARY = "----dshEventLoopBench"


def _multipart(payload: bytes, filename: str) -> tuple[bytes, str]:
    body = (
        f"--{BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("ascii") + payload + f"\r\n--{BOUNDARY}--\r\n".encode("ascii")
    return body, f"multipart/form-data; boundary={BOUNDARY}"


def post(base: str, endpoint: str, payload: bytes, filename: str, timeout: float) -> tuple[float, str]:
    """POST an image; return (elapsed_seconds, status_or_error_name)."""
    body, content_type = _multipart(payload, filename)
    request = urllib.request.Request(
        f"{base}{endpoint}", data=body, headers={"Content-Type": content_type}, method="POST"
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            return time.perf_counter() - start, str(response.status)
    except urllib.error.HTTPError as exc:
        return time.perf_counter() - start, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - report any transport failure as-is
        return time.perf_counter() - start, type(exc).__name__


def get(base: str, endpoint: str, timeout: float) -> tuple[float, str]:
    """GET an endpoint; return (elapsed_seconds, status_or_error_name)."""
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(f"{base}{endpoint}", timeout=timeout) as response:
            response.read()
            return time.perf_counter() - start, str(response.status)
    except urllib.error.HTTPError as exc:
        return time.perf_counter() - start, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return time.perf_counter() - start, type(exc).__name__


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8001", help="model-service base URL")
    parser.add_argument("--image", required=True, help="path to a test image")
    parser.add_argument("--endpoint", default="/detect", help="endpoint to saturate")
    parser.add_argument("--concurrency", type=int, default=16, help="parallel load requests")
    parser.add_argument("--health-samples", type=int, default=8, help="how many /health probes")
    parser.add_argument("--timeout", type=float, default=300.0, help="per-request timeout (s)")
    parser.add_argument(
        "--skip-warmup",
        action="store_true",
        help="skip the warmup request (use to measure a deliberately cold load)",
    )
    args = parser.parse_args()

    image = Path(args.image)
    payload = image.read_bytes()

    idle, idle_status = get(args.base, "/health", args.timeout)
    print(f"idle /health      : {idle * 1000:8.1f} ms  -> {idle_status}")

    if not args.skip_warmup:
        warm, warm_status = post(args.base, args.endpoint, payload, image.name, args.timeout)
        print(f"warmup {args.endpoint:<9}: {warm * 1000:8.1f} ms  -> {warm_status}")

    results: list[tuple[float, str]] = [None] * args.concurrency  # type: ignore[list-item]

    def worker(index: int) -> None:
        results[index] = post(args.base, args.endpoint, payload, image.name, args.timeout)

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(args.concurrency)]

    health: list[float] = []
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    # Let the load requests reach the server before sampling /health.
    time.sleep(0.05)
    for _ in range(args.health_samples):
        elapsed, _status = get(args.base, "/health", args.timeout)
        health.append(elapsed)

    for thread in threads:
        thread.join(args.timeout + 5)

    wall = time.perf_counter() - started
    durations = [d for d, _ in results if d is not None]
    statuses = sorted({s for _, s in results if s is not None})

    print(f"\nload: {args.concurrency} concurrent {args.endpoint}")
    print(
        f"  request ms      : min={min(durations) * 1000:8.1f}"
        f"  mean={statistics.mean(durations) * 1000:8.1f}"
        f"  max={max(durations) * 1000:8.1f}"
    )
    print(f"  statuses        : {', '.join(statuses)}")
    print(f"  wall clock      : {wall * 1000:8.1f} ms")

    print(f"\n/health DURING load (n={len(health)})")
    print(
        f"  ms              : min={min(health) * 1000:8.1f}"
        f"  mean={statistics.mean(health) * 1000:8.1f}"
        f"  max={max(health) * 1000:8.1f}"
    )
    ratio = max(health) / idle if idle > 0 else float("inf")
    print(f"  worst vs idle   : {ratio:8.1f}x")

    verdict = "EVENT LOOP FREE" if ratio < 5 or max(health) < 0.25 else "EVENT LOOP BLOCKED"
    print(f"\nverdict: {verdict}")
    return 0 if verdict == "EVENT LOOP FREE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
